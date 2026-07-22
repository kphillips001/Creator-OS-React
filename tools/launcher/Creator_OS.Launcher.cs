using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("Creator_OS")]
[assembly: AssemblyDescription("Creator_OS Windows Launcher")]
[assembly: AssemblyProduct("Creator_OS")]
[assembly: AssemblyCompany("Creator_OS")]
[assembly: AssemblyCopyright("Creator_OS")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

internal static class CreatorOsLauncher
{
    [STAThread]
    private static int Main()
    {
        string projectRoot = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(
            Path.DirectorySeparatorChar,
            Path.AltDirectorySeparatorChar
        );
        string launcherPath = Path.Combine(
            projectRoot,
            "tools",
            "launcher",
            "launch_creator_os.ps1"
        );

        if (!File.Exists(launcherPath))
        {
            MessageBox.Show(
                "Creator_OS could not find its PowerShell launcher:\n\n" + launcherPath,
                "Creator_OS",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }

        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File \"" + launcherPath + "\"",
                WorkingDirectory = projectRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };

            using (Process process = Process.Start(startInfo))
            {
                process.WaitForExit();
                if (process.ExitCode != 0)
                {
                    string failurePath = Path.Combine(projectRoot, "logs", "runtime", "launcher_failure.txt");
                    string failure = File.Exists(failurePath)
                        ? File.ReadAllText(failurePath).Trim()
                        : "No detailed failure report was produced.";
                    MessageBox.Show(
                        "Creator_OS did not start successfully.\n\n" + failure +
                        "\n\nReview logs\\runtime\\launcher.log for full diagnostics.",
                        "Creator_OS",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                }
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "Creator_OS could not start the PowerShell launcher:\n\n" + error.Message,
                "Creator_OS",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
    }
}
