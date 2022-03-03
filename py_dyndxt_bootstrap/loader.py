"""Injects and manages the Dynamic DXT loader."""

# pylint: disable=too-many-instance-attributes

import copy
import logging
import os
import struct
import time

from xboxpy.interface import if_xbdm
from .export_info import ExportInfo
from .py_dll_loader import DLLLoader
from . import xbdm_exports
from . import xboxkrnl_exports

logger = logging.getLogger(__name__)

_XBDM_HOOK_COMMAND_FMT = "resume thread=0x%X"
_XBDM_HOOK_EXPORT_INFO = xbdm_exports.DmResumeThread


class _DynamicDXTLoader:
    """Manages communication with the Dynamic DXT loader."""

    def __init__(self):
        self._bootstrapped = False
        self._bootstrap_path = None

        self._l1_bootstrap_path = None
        self._l1_bootstrap = None
        self._loader_path = None
        self._loader = None

        self._module_info = {}

        self._xbdm_hook_proc = None
        self._dm_allocate_pool_with_tag = None

    def set_bootstrap_path(self, path):
        """Sets the path to the Dynamic DXT 'lib' directory."""
        self._bootstrap_path = path

        self._l1_bootstrap_path = os.path.join(
            self._bootstrap_path, "bootstrap_l1.asm.obj"
        )
        self._loader_path = os.path.join(
            self._bootstrap_path, "libdynamic_dxt_loader.dll"
        )

    def load(self, dll_path):
        """Attempts to load the given Dynamic DXT DLL."""
        if not self._bootstrap():
            logger.debug("Bootstrap not installed and responsive")
            return False

        with open(dll_path, "rb") as dll_file:
            raw_image = dll_file.read()
        raw_image_len = len(raw_image)
        cmd = f"ddxt!load size=0x{raw_image_len:x}"

        # Relocating the DLL can take some time and if_xbdm's timeout may be
        # too short.
        old_timeout = if_xbdm.xbdm.gettimeout()
        if_xbdm.xbdm.settimeout(60)
        try:
            begin_time = time.monotonic()
            status, message = if_xbdm.xbdm_command(cmd, raw_image, raw_image_len)
        finally:
            end_time = time.monotonic()
            if_xbdm.xbdm.settimeout(old_timeout)

        logger.debug(f"DLL load took {end_time - begin_time} seconds")

        if status != 200:
            logger.error(f"Load failed: {status} {message}")
            return False
        else:
            logger.debug(f"Loaded {dll_path}: {message}")
        return True

    def _bootstrap(self):
        """Attempts to install the Dynamic DXT loader."""
        if self._bootstrapped:
            return True

        if self._check_loader_installed():
            return True

        if not self._bootstrap_path:
            raise Exception("Loader bootstrap path must be set via set_bootstrap_path.")

        self._prepare_bootstrap_dependencies()

        patch_memory = if_xbdm.GetMem(self._xbdm_hook_proc, len(self._l1_bootstrap))
        try:
            self._inject_loader()
        finally:
            if_xbdm.SetMem(self._xbdm_hook_proc, patch_memory)

        return self._check_loader_installed()

    def _check_loader_installed(self):
        status, message = if_xbdm.xbdm_command("ddxt!hello")
        if status != 200 and status != 202:
            return False
        logger.debug(f"Loader installed: {message}")
        self._bootstrapped = True
        return True

    def _prepare_bootstrap_dependencies(self):
        """Loads files and fetches memory addresses for the injection process."""
        self._load_bootstrap_files()

        self._fetch_base_address("xbdm.dll")
        self._module_info["xbdm.dll"]["exports"] = xbdm_exports.XBDM_EXPORTS

        self._fetch_base_address("xboxkrnl.exe")
        self._module_info["xboxkrnl.exe"][
            "exports"
        ] = xboxkrnl_exports.XBOXKERNL_EXPORTS

        self._xbdm_hook_proc = self._resolve_export_info(
            "xbdm.dll", _XBDM_HOOK_EXPORT_INFO
        )
        self._dm_allocate_pool_with_tag = self._resolve_export_info(
            "xbdm.dll", xbdm_exports.DmAllocatePoolWithTag
        )

    def _load_bootstrap_files(self):
        with open(self._l1_bootstrap_path, "rb") as infile:
            self._l1_bootstrap = infile.read()

        with open(self._loader_path, "rb") as infile:
            self._loader = infile.read()

    def _fetch_base_address(self, module_name):
        for module in if_xbdm.modules:
            if module["name"] == module_name:
                info = copy.deepcopy(module)
                self._module_info[module_name] = info
                image_base = module["base"]
                temp = _read_u32(image_base + 0x3C)
                temp = _read_u32(image_base + temp + 0x78)
                info["export_count"] = _read_u32(image_base + temp + 0x14)
                info["export_base"] = image_base + _read_u32(image_base + temp + 0x1C)
                return
        raise Exception(f"Failed to fetch module information for {module_name}")

    def _resolve_export_info(self, module: str, export_info: ExportInfo) -> int:
        if export_info.address is not None:
            return export_info.address

        info = self._module_info.get(module)
        if not info:
            raise Exception(f"Failed to resolve export for unknown module {module}")

        export_count = info["export_count"]
        export_base = info["export_base"]

        index = export_info.ordinal - 1
        if index >= export_count:
            raise Exception(
                f"Ordinal {export_info.ordinal} out of range for module {module}. Export count is "
                f"{export_count}."
            )

        method_address = info["base"] + _read_u32(export_base + index * 4)
        export_info.address = method_address

        return method_address

    def _inject_loader(self):
        if_xbdm.SetMem(self._xbdm_hook_proc, self._l1_bootstrap)

        # The last DWORD of the loader is used to set the requested size and fetch the
        # result.
        l1_bootstrap_len = len(self._l1_bootstrap)
        io_address = self._xbdm_hook_proc + l1_bootstrap_len - 4

        loader = DLLLoader(self._loader)
        loader.load(self._resolve_import_by_ordinal, self._resolve_import_by_name)

        if not loader.image_size:
            raise Exception("Loader is corrupt, image size == 0")

        _write_u32(io_address, loader.image_size)
        _invoke_bootstrap(self._dm_allocate_pool_with_tag)
        allocated_address = _read_u32(io_address)
        if not allocated_address:
            raise Exception("Failed to allocate memory for loader image.")

        if not loader.relocate(allocated_address):
            loader.free()
            raise Exception("Failed to relocate loader image.")

        begin_time = time.monotonic()
        if_xbdm.SetMem(allocated_address, loader.image)
        logger.debug(f"Bootstrap upload took {time.monotonic() - begin_time} seconds")

        # Put the L1 loader into entrypoint mode.
        _write_u32(io_address, 0)

        loader_entrypoint = loader.entry_point

        logger.debug(
            f"Loader installed at 0x{allocated_address:x} with entrypoint at "
            f"0x{loader_entrypoint:x}"
        )
        begin_time = time.monotonic()
        _invoke_bootstrap(loader_entrypoint)
        logger.debug(f"Bootstrap init took {time.monotonic() - begin_time} seconds")

        loader.free()

    def _resolve_import_by_ordinal(self, module_name, ordinal):
        info = self._module_info.get(module_name)
        if not info:
            logger.error(f"Failed to resolve export for unknown module {module_name}")
            return 0

        for export in info["exports"]:
            if export.ordinal == ordinal:
                return self._resolve_export_info(module_name, export)

        logger.error(f"Failed to resolve export {ordinal} in {module_name}")
        return 0

    def _resolve_import_by_name(self, module_name, export_name):
        info = self._module_info.get(module_name)
        if not info:
            logger.error(f"Failed to resolve export for unknown module {module_name}")
            return 0

        for export in info["exports"]:
            if export.name == export_name:
                return self._resolve_export_info(module_name, export)

        logger.error(f"Failed to resolve export {export_name} in {module_name}")
        return 0


def _invoke_bootstrap(arg):
    if_xbdm.xbdm_command(_XBDM_HOOK_COMMAND_FMT % arg)


# The helper functions in xboxpy use the same `resume` override as this loader and
# cannot be used.
def _write_u32(address, value):
    packed = struct.pack("<L", value)
    if_xbdm.SetMem(address, packed)


def _read_u32(address):
    value = if_xbdm.GetMem(address, 4)
    value = struct.unpack("<L", value)[0]
    return value


_loader = _DynamicDXTLoader()


def set_dyndxt_lib_path(path):
    """Sets the path to the dynamic ddxt 'lib' directory."""
    _loader.set_bootstrap_path(path)


def load(dll_path):
    """Attempts to load the given dynamic DXT DLL."""
    return _loader.load(dll_path)
