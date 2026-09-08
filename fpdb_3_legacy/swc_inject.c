/*
 * Minimal same-bitness DLL injector for the SwC Windows capture.
 *
 *     swc_inject.exe <pid> <absolute-dll-path>
 *
 * Windows has no LD_PRELOAD/DYLD_INSERT_LIBRARIES: a DLL is placed into an
 * already-running process by allocating the DLL path in the target and running
 * LoadLibraryW there via a remote thread. The command line is recovered with
 * the wide-character Windows API so paths outside the active ANSI code page
 * are preserved end to end.
 *
 * Exit codes are distinct so the Python launcher can report precisely which
 * step failed rather than a generic "injection failed".
 */

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN 1
#endif

#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

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

int main(void) {
    int argc = 0;
    LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argv == NULL || argc != 3) {
        fwprintf(stderr, L"usage: swc_inject <pid> <dll-path>\n");
        if (argv != NULL) {
            LocalFree(argv);
        }
        return INJ_USAGE;
    }

    wchar_t *end = NULL;
    unsigned long parsed_pid = wcstoul(argv[1], &end, 10);
    if (parsed_pid == 0 || end == argv[1] || *end != L'\0') {
        fwprintf(stderr, L"invalid pid: %ls\n", argv[1]);
        LocalFree(argv);
        return INJ_BAD_PID;
    }
    DWORD pid = (DWORD)parsed_pid;

    const wchar_t *dll_path = argv[2];
    SIZE_T path_bytes = (wcslen(dll_path) + 1) * sizeof(*dll_path);

    HANDLE process = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION |
                                     PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ,
                                 FALSE, pid);
    if (process == NULL) {
        fprintf(stderr, "OpenProcess failed (error %lu); try running as the same user\n",
                (unsigned long)GetLastError());
        LocalFree(argv);
        return INJ_OPEN_PROCESS;
    }

    /* Same-bitness check: this injector is 32-bit, so the target must be too.
     * Under 64-bit Windows that means it must be a WOW64 process. */
#ifdef _WIN64
    int injector_wow64 = 0; /* a 64-bit injector is never WOW64 */
#else
    BOOL os_is_64 = FALSE;
    IsWow64Process(GetCurrentProcess(), &os_is_64);
    int injector_wow64 = os_is_64 ? 1 : 0;
#endif
    if (is_wow64(process) != injector_wow64) {
        fprintf(stderr, "bitness mismatch: the injector and the target must both be 32-bit\n");
        CloseHandle(process);
        LocalFree(argv);
        return INJ_BITNESS;
    }

    void *remote_path = VirtualAllocEx(process, NULL, path_bytes, MEM_COMMIT | MEM_RESERVE,
                                       PAGE_READWRITE);
    if (remote_path == NULL) {
        fprintf(stderr, "VirtualAllocEx failed (error %lu)\n", (unsigned long)GetLastError());
        CloseHandle(process);
        LocalFree(argv);
        return INJ_ALLOC;
    }

    if (!WriteProcessMemory(process, remote_path, dll_path, path_bytes, NULL)) {
        fprintf(stderr, "WriteProcessMemory failed (error %lu)\n", (unsigned long)GetLastError());
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
        CloseHandle(process);
        LocalFree(argv);
        return INJ_WRITE;
    }

    /* The injector and target have the same bitness, so kernel32 is mapped at
     * the same address in both processes on a given boot. Use LoadLibraryW so
     * the wide path written above is consumed without an ANSI-codepage round trip. */
    HMODULE kernel32 = GetModuleHandleW(L"kernel32.dll");
    FARPROC load_library = kernel32 ? GetProcAddress(kernel32, "LoadLibraryW") : NULL;
    if (load_library == NULL) {
        fprintf(stderr, "could not resolve LoadLibraryW\n");
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
        CloseHandle(process);
        LocalFree(argv);
        return INJ_LOADLIB;
    }

    HANDLE thread = CreateRemoteThread(process, NULL, 0, (LPTHREAD_START_ROUTINE)load_library,
                                       remote_path, 0, NULL);
    if (thread == NULL) {
        fprintf(stderr, "CreateRemoteThread failed (error %lu)\n", (unsigned long)GetLastError());
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
        CloseHandle(process);
        LocalFree(argv);
        return INJ_THREAD;
    }

    int status = INJ_OK;
    if (WaitForSingleObject(thread, 30000) != WAIT_OBJECT_0) {
        fprintf(stderr, "the injected LoadLibrary did not return within 30s\n");
        status = INJ_TIMEOUT;
    } else {
        DWORD exit_code = 0;
        GetExitCodeThread(thread, &exit_code);
        if (exit_code == 0) {
            fprintf(stderr, "LoadLibrary in the target returned NULL; the DLL failed to load\n");
            status = INJ_LOAD_FAILED;
        }
    }

    CloseHandle(thread);
    VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
    CloseHandle(process);
    LocalFree(argv);
    return status;
}
