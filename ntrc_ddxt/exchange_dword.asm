bits 32

SECTION .TEXT
        GLOBAL ExchangeDWORD

; DWORD ExchangeDWORD(intptr_t address, DWORD value)
ExchangeDWORD:
        ; Avoid any other CPU stuff overwriting stuff in this risky section
        cli

        ; address
        mov edx, dword [esp+4]

        ; value
        mov eax, dword [esp+8]

        xchg dword [edx], eax

        sti

        ret 0x8
