#!/usr/bin/env python3

"""Tool to capture nv2a activity from an xbox."""

# pylint: disable=missing-function-docstring
# pylint: disable=consider-using-f-string
# pylint: disable=too-few-public-methods
# pylint: disable=too-many-locals

import argparse
import atexit
import logging
import os
import signal
import sys
import time

from AbortFlag import AbortFlag
import py_dyndxt_bootstrap
import ntrc_ddxt
import Trace
from util import ansi_formatter
from util import debug_logging
from Xbox import Xbox
import XboxHelper

logger = logging.getLogger(__name__)

# pylint: disable=invalid-name
# TODO: Remove tiling suppression once AGP read in Texture.py is fully proven.
_enable_experimental_disable_z_compression_and_tiling = False
# pylint: enable=invalid-name


def experimental_disable_z_compression_and_tiling(xbox):
    # Disable Z-buffer compression and Tiling
    # FIXME: This is a dirty dirty hack which breaks PFB and PGRAPH state!
    NV10_PGRAPH_RDI_INDEX = 0xFD400750
    NV10_PGRAPH_RDI_DATA = 0xFD400754
    for i in range(8):

        # This is from a discussion on nouveau IRC:
        #  mwk: the RDI copy is for texturing
        #  mwk: the mmio PGRAPH copy is for drawing to the framebuffer

        # Disabling Z-Compression seems to work fine
        def disable_z_compression(index):
            zcomp = xbox.read_u32(0xFD100300 + 4 * index)
            zcomp &= 0x7FFFFFFF
            xbox.write_u32(0xFD100300 + 4 * index, zcomp)  # PFB
            xbox.write_u32(0xFD400980 + 4 * index, zcomp)  # PGRAPH
            # PGRAPH RDI
            # FIXME: This scope should be atomic
            xbox.write_u32(NV10_PGRAPH_RDI_INDEX, 0x00EA0090 + 4 * index)
            xbox.write_u32(NV10_PGRAPH_RDI_DATA, zcomp)

        disable_z_compression(i)

        # Disabling tiling entirely
        def disable_tiling(index):
            tile_addr = xbox.read_u32(0xFD100240 + 16 * index)
            tile_addr &= 0xFFFFFFFE
            xbox.write_u32(0xFD100240 + 16 * index, tile_addr)  # PFB
            xbox.write_u32(0xFD400900 + 16 * index, tile_addr)  # PGRAPH
            # PGRAPH RDI
            # FIXME: This scope should be atomic
            xbox.write_u32(NV10_PGRAPH_RDI_INDEX, 0x00EA0010 + 4 * index)
            xbox.write_u32(NV10_PGRAPH_RDI_DATA, tile_addr)
            # xbox.write_u32(NV10_PGRAPH_RDI_INDEX, 0x00EA0030 + 4 * i)
            # xbox.write_u32(NV10_PGRAPH_RDI_DATA, tile_limit)
            # xbox.write_u32(NV10_PGRAPH_RDI_INDEX, 0x00EA0050 + 4 * i)
            # xbox.write_u32(NV10_PGRAPH_RDI_DATA, tile_pitch)

        disable_tiling(i)


def _load_ntrc():
    build_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "build")
    py_dyndxt_bootstrap.set_dyndxt_lib_path(os.path.join(build_path, "ddxt", "lib"))
    py_dyndxt_bootstrap.set_bootstrap_lib_path(
        os.path.join(build_path, "py_dyndxt_bootstrap", "lib")
    )
    if not py_dyndxt_bootstrap.load(os.path.join(build_path, "libntrc_ddxt.dll")):
        raise Exception("Failed to inject ntrc tracer")
    tracer = ntrc_ddxt.NTRC()
    if not tracer.connect():
        raise Exception("ntrc tracer installed but not responsive")
    logger.debug("NTRC module installed successfully")

    tracer.startup()
    logger.debug("NTRC tracer started, waiting for idle state")

    tracer.wait_for_idle_state(5)

    return tracer


def main(args):

    os.makedirs(args.out, exist_ok=True)

    xbox = Xbox()
    xbox_helper = XboxHelper.XboxHelper(xbox)

    if args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(level=log_level)
    if args.color:
        ansi_formatter.colorize_logs()

    abort_flag = AbortFlag()

    def signal_handler(_signal, _frame):
        if not abort_flag.should_abort:
            print("Got first SIGINT! Aborting..")
            abort_flag.abort()
        else:
            print("Got second SIGINT! Forcing exit")
            sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    ntrc_tracer = _load_ntrc()
    atexit.register(ntrc_tracer.shutdown)

    logger.info("Awaiting stable PB state")
    dma_push_addr, dma_pull_addr = ntrc_tracer.wait_for_stable_push_buffer_state()

    if not dma_pull_addr or not dma_push_addr or abort_flag.should_abort:
        if not abort_flag.should_abort:
            logger.error("Failed to reach stable state.")
        return

    if args.wait_for_first_frame:
        logger.info("Discarding until start of frame")
        ntrc_tracer.discard_until_next_frame()

    logger.info("Stepping through PB")

    # Start measuring time
    begin_time = time.monotonic()

    if _enable_experimental_disable_z_compression_and_tiling:
        # TODO: Enable after removing FIXME above.
        experimental_disable_z_compression_and_tiling(xbox)

    # Create a new trace object
    pixel_dumping = not args.no_pixel
    enable_texture_dumping = pixel_dumping and not args.no_texture
    enable_surface_dumping = pixel_dumping and not args.no_surface
    enable_raw_pixel_dumping = not args.no_raw_pixel
    enable_rdi = pixel_dumping and not args.no_rdi

    if args.alpha_mode == "both":
        alpha_mode = Trace.Tracer.ALPHA_MODE_BOTH
    elif args.alpha_mode == "keep":
        alpha_mode = Trace.Tracer.ALPHA_MODE_KEEP
    else:
        alpha_mode = Trace.Tracer.ALPHA_MODE_DROP

    trace = Trace.Tracer(
        dma_pull_addr,
        dma_push_addr,
        xbox,
        xbox_helper,
        abort_flag,
        output_dir=args.out,
        alpha_mode=alpha_mode,
        enable_texture_dumping=enable_texture_dumping,
        enable_surface_dumping=enable_surface_dumping,
        enable_raw_pixel_dumping=enable_raw_pixel_dumping,
        enable_rdi=enable_rdi,
        verbose=args.verbose,
        max_frames=args.max_flip,
    )

    # Dump the initial state
    trace.command_count = -1
    trace.dump_surfaces(xbox, None)
    trace.command_count = 0

    trace.run()

    # Recover the real address
    xbox.write_u32(XboxHelper.DMA_PUSH_ADDR, trace.real_dma_push_addr)

    logger.info("Finished PB")

    # We can continue the cache updates now.
    xbox_helper.resume_fifo_pusher()

    # Finish measuring time
    end_time = time.monotonic()
    duration = end_time - begin_time

    command_count = trace.recorded_command_count
    print(
        "Recorded %d flip stalls and %d PB commands (%.2f commands / second)"
        % (trace.recorded_flip_stall_count, command_count, command_count / duration)
    )


if __name__ == "__main__":

    def _parse_args():
        parser = argparse.ArgumentParser()

        parser.add_argument(
            "-o",
            "--out",
            metavar="path",
            default="out",
            help="Set the output directory.",
        )

        parser.add_argument(
            "--no-surface", help="Disable dumping of surfaces.", action="store_true"
        )

        parser.add_argument(
            "--no-texture", help="Disable dumping of textures.", action="store_true"
        )

        parser.add_argument(
            "--no-pixel",
            help="Disable dumping of all graphical resources (surfaces, textures).",
            action="store_true",
        )

        parser.add_argument(
            "--no-raw-pixel",
            help="Disable raw memory dumping of all graphical resources (surfaces, textures).",
            action="store_true",
        )

        parser.add_argument(
            "--no-rdi",
            help="Disable dumping of RDI.",
            action="store_true",
        )

        parser.add_argument(
            "--alpha-mode",
            default="drop",
            choices=["drop", "keep", "both"],
            help=(
                "Define how the alpha channel is handled in color graphical resources.\n"
                "  drop: Discard the alpha channel\n"
                "  keep: Save the alpha channel\n"
                "  drop: Save two dumps, one with the alpha channel and one without\n"
            ),
        )

        parser.add_argument(
            "-v",
            "--verbose",
            help="Enable verbose debug output.",
            action="store_true",
        )

        parser.add_argument(
            "--color",
            help="Colorize messages.",
            action="store_true",
        )

        parser.add_argument(
            "--max-flip",
            metavar="frames",
            default=0,
            type=int,
            help="Exit tracing after the given number of frame swaps.",
        )

        parser.add_argument(
            "--wait_for_first_frame",
            help="Start tracing only after the next NV097_FLIP_STALL.",
            action="store_true",
        )

        return parser.parse_args()

    sys.exit(main(_parse_args()))
