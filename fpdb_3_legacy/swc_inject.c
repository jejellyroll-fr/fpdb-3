/*
 * Minimal same-bitness DLL injector for the SwC Windows capture.
 *
 *     swc_inject.exe <pid> <absolute-dll-path>
 *
 * Windows has no LD_PRELOAD/DYLD_INSERT_LIBRARIES: a DLL is placed into an
 * already-running process by allocating the DLL path in the target and running
 * LoadLibraryW there via a remote thread. That thread's entry point must be the
 * *target's* LoadLibraryW address; kernel32.dll is loaded at the same base in
 * every process of the same bitness on a given boot, so the address this
 * injector resolves is valid in the target only when both are the same
 * bitness. The SwC Windows client is 32-bit, so this injector is built 32-bit
 * too (see swc_tap_build) and refuses a target whose bitness differs.
 *
 * Exit codes are distinct so the Python launcher can report precisely which
 * step failed rather than a generic "injection failed".
 */

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN 1
#endif

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    INJ_OK = 0,
    INJ_USAGE = 2,
    INJ_BAD_PID = 3,
    INJ_OPEN_PROCESS = 4,
    INJ_BITNESS = 5,
    INJ_ALLOC = 6,
    INJ_WRITE = 7,
    INJ_LOADLIB = 8,
    INJ_THREAD = 9,
    INJ_TIMEOUT = 10,
    INJ_LOAD_FAILED = 11,
};

/* True when the target process runs under WOW64 (a 32-bit process on 64-bit
 * Windows). A 32-bit injector matches a WOW64 target; on 32-bit Windows both
 * this injector and the target report FALSE, which also matches. */
static int is_wow64(HANDLE process) {
    BOOL wow = FALSE;
    IsWow64Process(process, &wow);
    return wow ? 1 : 0;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: swc_inject <pid> <dll-path>\n");
        return INJ_USAGE;
    }

    DWORD pid = (DWORD)strtoul(argv[1], NULL, 10);
    if (pid == 0) {
        fprintf(stderr, "invalid pid: %s\n", argv[1]);
        return INJ_BAD_PID;
    }

    const char *dll_path = argv[2];
    size_t path_bytes = strlen(dll_path) + 1;

    HANDLE process = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION |
                                     PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ,
                                 FALSE, pid);
    if (process == NULL) {
        fprintf(stderr, "OpenProcess failed (error %lu); try running as the same user\n",
                (unsigned long)GetLastError());
        return INJ_OPEN_PROCESS;
    }

    /* Same-bitness check: this injector is 32-bit, so the target must be too.
     * Under 64-bit Windows that means it must be a WOW64 process. */
#ifdef _WIN64
    int injector_wow64 = 0; /* a 64-bit injector is never WOW64 */
#else
    BOOL os_is_64 = FALSE;
    /* On 32-bit Windows every process is 32-bit; on 64-bit Windows this 32-bit
     * injector is itself WOW64. Either way the target must match is_wow64(self). */
    IsWow64Process(GetCurrentProcess(), &os_is_64);
    int injector_wow64 = os_is_64 ? 1 : 0;
#endif
    if (is_wow64(process) != injector_wow64) {
        fprintf(stderr, "bitness mismatch: the injector and the target must both be 32-bit\n");
        CloseHandle(process);
        return INJ_BITNESS;
    }

    void *remote_path = VirtualAllocEx(process, NULL, path_bytes, MEM_COMMIT | MEM_RESERVE,
                                       PAGE_READWRITE);
    if (remote_path == NULL) {
        fprintf(stderr, "VirtualAllocEx failed (error %lu)\n", (unsigned long)GetLastError());
        CloseHandle(process);
        return INJ_ALLOC;
    }

    if (!WriteProcessMemory(process, remote_path, dll_path, path_bytes, NULL)) {
        fprintf(stderr, "WriteProcessMemory failed (error %lu)\n", (unsigned long)GetLastError());
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
        CloseHandle(process);
        return INJ_WRITE;
    }

    /* LoadLibraryA lives in kernel32 at the same address in the target as here
     * (same bitness), so its address in this process is valid there. Using the
     * ANSI variant lets us hand over the path as a plain byte string. */
    HMODULE kernel32 = GetModuleHandleA("kernel32.dll");
    FARPROC load_library = kernel32 ? GetProcAddress(kernel32, "LoadLibraryA") : NULL;
    if (load_library == NULL) {
        fprintf(stderr, "could not resolve LoadLibraryA\n");
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
        CloseHandle(process);
        return INJ_LOADLIB;
    }

    HANDLE thread = CreateRemoteThread(process, NULL, 0, (LPTHREAD_START_ROUTINE)load_library,
                                       remote_path, 0, NULL);
    if (thread == NULL) {
        fprintf(stderr, "CreateRemoteThread failed (error %lu)\n", (unsigned long)GetLastError());
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
        CloseHandle(process);
        return INJ_THREAD;
    }

    int status = INJ_OK;
    if (WaitForSingleObject(thread, 30000) != WAIT_OBJECT_0) {
        fprintf(stderr, "the injected LoadLibrary did not return within 30s\n");
        status = INJ_TIMEOUT;
    } else {
        DWORD exit_code = 0;
        GetExitCodeThread(thread, &exit_code);
        /* LoadLibrary's return (the HMODULE, truncated to 32 bits) is 0 only on
         * failure. A non-zero value means the DLL loaded and DllMain ran. */
        if (exit_code == 0) {
            fprintf(stderr, "LoadLibrary in the target returned NULL; the DLL failed to load\n");
            status = INJ_LOAD_FAILED;
        }
    }

    CloseHandle(thread);
    VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
    CloseHandle(process);
    return status;
}
