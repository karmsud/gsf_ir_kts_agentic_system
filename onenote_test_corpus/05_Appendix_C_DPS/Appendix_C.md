# Appendix C — Drive Protection System (DPS)

C
Drive Protection System (DPS)
The Drive Protection System (DPS) is a diagnostic tool built into the
hard drives installed in select computers. DPS is designed to help
diagnose problems that might result in unwarranted hard drive
replacement.
When these systems are built, each installed hard drive is tested using
DPS, and a permanent record of key information is written onto the
drive. Each time DPS is run, test results are written to the hard drive.
Your service provider can use this information to help diagnose
conditions that caused you to run the DPS software.
Running DPS will not affect any programs or data stored on the hard
drive. The test resides in the hard drive firmware and can be executed
even if the computer will not boot to an operating system. The time
required to execute the test depends on the manufacturer and size
of the hard drive; in most cases, the test will take approximately
two minutes per gigabyte.
Use DPS when you suspect a hard drive problem. If the computer
reports a SMART Hard Drive Detect Imminent Failure message, there
is no need to run DPS; instead, back up the information on the hard
drive and contact a service provider for a replacement hard drive.
Troubleshooting Guide www.hp.com C–1

Drive Protection System (DPS)
Accessing DPS Through Diagnostics for Windows
To access DPS through Diagnostics for Windows, perform the
following steps:
1. Turn on the computer and select Start > Control Panel >
Diagnostics for Windows.
A choice of five possible headings appears in the Diagnostics
screen: Overview, Test, Status, Log, and Error.
2. Select Test > Type of Test.
A choice of three tests appear: Quick Test, Complete Test, and
Custom Test.
3. Select Custom Test.
A choice of two test modes is offered: Interactive Mode and
Unattended Mode.
4. Select Interactive Test > Storage > Hard Drives.
5. Select the specific drives to be tested > Drive Protection System
Test > Begin Testing.
When the test has been completed, one of three messages will be
displayed for each of the drives tested:
■ Test Succeeded. Completion Code 0.
■ Test Aborted. Completion Code 1 or 2.
■ Test Failed. Drive Replacement Recommended. Completion
Code 3 through 14.
If the test failed, the completion code should be recorded and reported
to your service provider for help in diagnosing the computer problem.
C–2 www.hp.com Troubleshooting Guide

Drive Protection System (DPS)
Accessing DPS Through Computer Setup
When the computer does not power on properly you should use
Computer Setup to access the DPS program. To access DPS, perform
the following steps:
1. Turn on or restart the computer.
2. When the F10 Setup message appears in the lower-right corner of
the screen, press the F10 key.
✎
If you do not press the F10 key while the message is displayed, you
must turn the computer off, then on again, to access the utility.
A choice of five headings appears in the Computer Setup Utilities
menu: File, Storage, Security, Power, and Advanced.
3. Select Storage > DPS Self-Test.
The screen will display the list of DPS-capable hard drives that
are installed on the computer.
✎
If no DPS-capable hard drives are installed, the DPS Self-Test option
will not appear on the screen.
4. Select the hard drive to be tested and follow the screen prompts to
complete the testing process.
When the test has been completed, one of three messages will be
displayed:
■ Test Succeeded. Completion Code 0.
■ Test Aborted. Completion Code 1 or 2.
■ Test Failed. Drive Replacement Recommended. Completion
Code 3 through 14.
If the test failed, the completion code should be recorded and reported
to your service provider for help in diagnosing the computer problem.
Troubleshooting Guide www.hp.com C–3

Drive Protection System (DPS)
C–4 www.hp.com Troubleshooting Guide
