# Запуск процесса на отдельном (невидимом) рабочем столе Windows.
#
# Зачем: сценарный прогон Vanessa открывает окна тест-менеджера и тест-клиента 1С на
# текущем рабочем столе и забивает монитор. Vanessa управляет клиентом по протоколу
# тест-менеджера, а не мышью, - видимость и фокус ей не нужны. Процесс, запущенный с
# STARTUPINFO.lpDesktop на своём рабочем столе, работает там вместе со всеми дочерними
# процессами (они наследуют рабочий стол родителя), и пользователь их не видит.
#
# Ограничение: снимки экрана с невидимого стола могут выйти пустыми.
#
# Add-Type компилирует тип один раз на процесс PowerShell: после правки C#-части
# нужен новый процесс, иначе отработает старая сборка.

if (-not ('Agent1C.HiddenDesktop' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace Agent1C {
    public static class HiddenDesktop {
        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        static extern IntPtr CreateDesktop(string lpszDesktop, IntPtr lpszDevice, IntPtr pDevmode,
            int dwFlags, uint dwDesiredAccess, IntPtr lpsa);
        [DllImport("user32.dll", SetLastError = true)]
        static extern bool CloseDesktop(IntPtr hDesktop);

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct STARTUPINFO {
            public int cb; public string lpReserved; public string lpDesktop; public string lpTitle;
            public int dwX; public int dwY; public int dwXSize; public int dwYSize;
            public int dwXCountChars; public int dwYCountChars; public int dwFillAttribute; public int dwFlags;
            public short wShowWindow; public short cbReserved2; public IntPtr lpReserved2;
            public IntPtr hStdInput; public IntPtr hStdOutput; public IntPtr hStdError;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct PROCESS_INFORMATION { public IntPtr hProcess; public IntPtr hThread; public int dwProcessId; public int dwThreadId; }

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        static extern bool CreateProcess(string lpApplicationName, StringBuilder lpCommandLine, IntPtr lpProcessAttributes,
            IntPtr lpThreadAttributes, bool bInheritHandles, uint dwCreationFlags, IntPtr lpEnvironment,
            string lpCurrentDirectory, ref STARTUPINFO lpStartupInfo, out PROCESS_INFORMATION lpProcessInformation);
        [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr hHandle, uint dwMilliseconds);
        [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr hProcess, out uint lpExitCode);
        [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr hProcess, uint uExitCode);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr hObject);

        const uint GENERIC_ALL = 0x10000000;
        // Консоль БЕЗ окна, а не новая консоль: на Windows 11 терминал по умолчанию
        // (Windows Terminal) перехватывает создание консольного окна и открывает вкладку
        // на рабочем столе пользователя, игнорируя lpDesktop. Дочерние консольные
        // процессы (vrunner через -NoNewWindow) наследуют эту безоконную консоль.
        const uint CREATE_NO_WINDOW = 0x08000000;
        const uint WAIT_TIMEOUT = 0x00000102;

        // Возвращает код выхода процесса; -1 - процесс снят по таймауту.
        public static int Run(string desktopName, string commandLine, string workingDirectory, int timeoutMs) {
            IntPtr desktop = CreateDesktop(desktopName, IntPtr.Zero, IntPtr.Zero, 0, GENERIC_ALL, IntPtr.Zero);
            if (desktop == IntPtr.Zero)
                throw new InvalidOperationException("CreateDesktop: ошибка " + Marshal.GetLastWin32Error());
            try {
                STARTUPINFO si = new STARTUPINFO();
                si.cb = Marshal.SizeOf(typeof(STARTUPINFO));
                si.lpDesktop = "WinSta0\\" + desktopName;
                PROCESS_INFORMATION pi;
                if (!CreateProcess(null, new StringBuilder(commandLine), IntPtr.Zero, IntPtr.Zero, false,
                        CREATE_NO_WINDOW, IntPtr.Zero, workingDirectory, ref si, out pi))
                    throw new InvalidOperationException("CreateProcess: ошибка " + Marshal.GetLastWin32Error());
                try {
                    uint wait = WaitForSingleObject(pi.hProcess, timeoutMs <= 0 ? 0xFFFFFFFF : (uint)timeoutMs);
                    if (wait == WAIT_TIMEOUT) { TerminateProcess(pi.hProcess, 1); return -1; }
                    uint code; GetExitCodeProcess(pi.hProcess, out code);
                    return (int)code;
                } finally { CloseHandle(pi.hThread); CloseHandle(pi.hProcess); }
            } finally { CloseDesktop(desktop); }
        }
    }
}
'@
}

function Invoke-OnHiddenDesktop {
    <# Запускает командную строку на своём невидимом рабочем столе и ждёт выхода.
       Возвращает код выхода; -1 - снят по таймауту. #>
    param(
        [Parameter(Mandatory)][string]$CommandLine,
        [string]$WorkingDirectory = (Get-Location).Path,
        [int]$TimeoutMinutes = 60,
        [string]$DesktopName = ('agent1c-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    )
    return [Agent1C.HiddenDesktop]::Run($DesktopName, $CommandLine, $WorkingDirectory, $TimeoutMinutes * 60000)
}
