/* Compiled by the GNU parity workflow into an object, a shared library and an
 * executable, so compare_gnu.py sees a thin object of each kind with strings in
 * every kind of section: read-only data, writable data, wide strings, code and
 * zero-filled data that -d must skip. The u"" and U"" arrays use stdint's
 * types because macOS has no <uchar.h>. */
#include <stdint.h>
#include <wchar.h>

const char rodata_string[] = "read-only data string";
char data_string[] = "writable data string";
const uint_least16_t utf16_string[] = u"a UTF-16 string";
const uint_least32_t utf32_string[] = U"a UTF-32 string";
const wchar_t wide_string[] = L"a wchar_t string";
char bss_buffer[4096];

const char *pick(int which) {
    switch (which) {
    case 0:
        return rodata_string;
    case 1:
        return data_string;
    default:
        bss_buffer[0] = (char)(utf16_string[0] ^ utf32_string[0]);
        return (const char *)wide_string;
    }
}

int main(int argc, char **argv) {
    (void)argv;
    return pick(argc)[0] == '\0';
}
