# Appendix A — POST Error Messages

A
POST Error Messages
This appendix lists the error codes, error messages, and the various
indicator light and audible sequences that you may encounter during
Power-On Self-Test (POST) or computer restart, the probable source
of the problem, and steps you can take to resolve the error condition.
POST Message Disabled suppresses most system messages during
POST, such as memory count and non-error text messages. If a POST
error occurs, the screen will display the error message. To manually
switch to the POST Messages Enabled mode during POST, press any
key (except F10 or F12). The default mode is POST Message
Disabled.
The speed at which the computer loads the operating system and the
extent to which it is tested are determined by the POST mode
selection.
Quick Boot is a fast startup process that does not run all of the system
level tests, such as the memory test. Full Boot runs all of the
ROM-based system tests and takes longer to complete.
Full Boot may also be enabled to run every 1 to 30 days on a regularly
scheduled basis. To establish the schedule, reconfigure the computer
to the Full Boot Every x Days mode, using Computer Setup.
✎
For more information on Computer Setup, see the Computer Setup
(F10) Utility Guide on the Documentation CD.
Troubleshooting Guide www.hp.com A–1

POST Error Messages
POST Numeric Codes and Text Messages
This section covers those POST errors that have numeric codes
associated with them. The section also includes some text messages
that may be encountered during POST.
✎
The computer will beep once after a POST text message is displayed
on the screen.
Numeric Codes and Text Messages
Code/Message Probable Cause Recommended Action
101-Option ROM System ROM or 1. Verify the correct ROM.
Checksum Error expansion board option
2. Flash the ROM if needed.
ROM checksum.
3. If an expansion board was recently
added, remove it to see if the problem
remains.
4. Clear CMOS. (See Appendix B,
“Password Security and Resetting
CMOS.”)
5. If the message disappears, there may
be a problem with the expansion
card.
6. Replace the system board.
102-System Board DMA or timers. 1. Clear CMOS. (See Appendix B,
Failure “Password Security and Resetting
CMOS.”)
2. Remove expansion boards.
3. Replace the system board.
103-System Board DMA or timers. 1. Clear CMOS. (See Appendix B,
Failure “Password Security and Resetting
CMOS.”)
2. Remove expansion boards.
3. Replace the system board.
A–2 www.hp.com Troubleshooting Guide

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
110-Out of Memory Recently added PCI 1. If a PCI expansion card was recently
Space for Option expansion card contains added, remove it to see if the problem
ROMs an option ROM too large remains.
to download during
2. In Computer Setup, set Advanced >
POST.
Device Options > NIC PXE
Option ROM Download to
DISABLE to prevent PXE option ROM
for the internal NIC from being
downloaded during POST to free
more memory for an expansion card's
option ROM. Internal PXE option
ROM is used for booting from the NIC
to a PXE server.
3. Enable the ACPI/USB Buffers @ Top
of Memory setting in Computer Setup.
150-SafePost Active A PCI expansion card is 1. Restart the computer.
not responding.
2. Disable SafePost.
3. If the expansion card does not
respond, replace the card.
162-System Options Configuration incorrect. Run Computer Setup and check the
Not Set RTC (real-time clock) configuration in Advanced >
Onboard Devices.
battery may need to
be replaced. Reset the date and time under Control
Panel. If the problem persists, replace the
RTC battery. See the Hardware Reference
Guide on the Documentation CD for
instructions on installing a new battery, or
contact an authorized dealer or reseller
for RTC battery replacement.
Troubleshooting Guide www.hp.com A–3

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
163-Time & Date Invalid time or date in Reset the date and time under Control
Not Set configuration memory. Panel (Computer Setup can also be
used). If the problem persists, replace the
RTC (real-time clock)
RTC battery. See the Hardware Reference
battery may need to
Guide on the Documentation CD for
be replaced.
instructions on installing a new battery, or
contact an authorized dealer or reseller
for RTC battery replacement.
CMOS jumper may not Check for proper placement of the CMOS
be properly installed. jumper if applicable.
164-Memory Size Memory amount has Press the F1 key to save the memory
Error changed since the last changes.
boot (memory added or
removed).
Memory configuration 1. Run Computer Setup or Windows
incorrect. utilities.
2. Make sure the memory module(s) are
installed properly.
3. If third-party memory has been
added, test using HP-only memory.
4. Verify proper memory module type.
201-Memory Error RAM failure. 1. Run Computer Setup or Windows
utilities.
2. Ensure memory modules are correctly
installed.
3. Verify proper memory module type.
4. Remove and replace the memory
module(s) one at a time to isolate the
faulty module.
5. Replace faulty memory module(s).
6. If the error persists after replacing
memory modules, replace the system
board.
A–4 www.hp.com Troubleshooting Guide

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
202-Memory Type Memory modules do not Replace memory modules with matched
Mismatch match each other. sets.
213-Incompatible A memory module 1. Verify proper memory module type.
Memory Module in in memory socket
2. Try another memory socket.
Memory Socket(s) X, identified in the error
3. Replace DIMM with a module
X, ... message is missing
conforming to the SPD standard.
critical SPD information,
or is incompatible with
the chipset.
214-DIMM A specific error has 1. Verify proper memory module type.
Configuration occurred in a memory
2. Try another memory socket.
Warning device installed in the
3. Replace memory module if problem
identified socket.
persists.
219-ECC Memory Recently added memory 1. If additional memory was recently
Module Detected module(s) support ECC added, remove it to see if the problem
ECC Modules not memory error correction. remains.
supported on this
2. Check product documentation for
Platform
memory support information.
301-Keyboard Error Keyboard failure. 1. Reconnect keyboard with computer
turned off.
2. Check connector for bent or missing
pins.
3. Ensure that none of the keys are
depressed.
4. Replace keyboard.
303-Keyboard I/O board keyboard 1. Reconnect keyboard with computer
Controller Error controller. turned off.
2. Replace the system board.
Troubleshooting Guide www.hp.com A–5

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
304-Keyboard or Keyboard failure. 1. Reconnect the keyboard with
System Unit Error computer turned off.
2. Ensure that none of the keys are
depressed.
3. Replace the keyboard.
4. Replace the system board.
404-Parallel Port Both external and 1. Remove any parallel port expansion
Address Conflict internal ports are cards.
Detected assigned to
2. Clear CMOS. (See Appendix B,
parallel port X.
“Password Security and Resetting
CMOS.”)
3. Reconfigure card resources and/or
run Computer Setup.
410-Audio Interrupt IRQ address conflicts Enter Computer Setup and reset the IRQ in
Conflict with another device. Advanced > Onboard Devices.
411-Network IRQ address conflicts Enter Computer Setup and reset the IRQ in
Interface Card with another device. Advanced > Onboard Devices.
Interrupt Conflict
501-Display Graphics display 1. Reseat the graphics card
Adapter Failure controller. (if applicable).
2. Clear CMOS. (See Appendix B,
“Password Security and Resetting
CMOS.”)
3. Verify monitor is attached and turned
on.
4. Replace the graphics card (if
possible).
510-Splash Screen Splash Screen image has Install latest version of ROMPaq to restore
Image Corrupted errors. image.
511-CPU, CPUA, or CPU fan is not connected 1. Reseat CPU fan.
CPUB Fan not or may have
2. Reseat fan cable.
Detected malfunctioned.
3. Replace CPU fan.
A–6 www.hp.com Troubleshooting Guide

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
512-Chassis, Rear Chassis, rear chassis, or 1. Reseat chassis, rear chassis, or front
Chassis, or Front front chassis fan is not chassis fan.
Chassis Fan not connected or may have
2. Reseat fan cable.
Detected malfunctioned.
3. Replace chassis, rear chassis, or front
chassis fan.
514-CPU or Chassis CPU or chassis fan is not 1. Reseat CPU or chassis fan.
Fan not Detected connected or may have
2. Reseat fan cable.
malfunctioned.
3. Replace CPU or chassis fan.
601-Diskette Diskette controller 1. Run Computer Setup.
Controller Error circuitry or floppy drive
2. Check and/or replace cables.
circuitry incorrect.
3. Clear CMOS. (See Appendix B,
“Password Security and Resetting
CMOS.”)
4. Replace diskette drive.
5. Replace the system board.
605-Diskette Drive Mismatch in drive type. 1. Run Computer Setup.
Type Error
2. Disconnect any other diskette
controller devices (tape drives).
3. Clear CMOS. (See Appendix B,
“Password Security and Resetting
CMOS.”)
610-External External tape drive not Reinstall tape drive or press F1 and allow
Storage Device connected. system to reconfigure without the drive.
Failure
611-Primary Floppy Configuration error. Run Computer Setup and check the
Port Address configuration in Advanced >
Assignment Conflict Onboard Devices.
660-Display cache Integrated graphics Replace system board if minimal graphics
is detected controller display cache degrading is an issue.
unreliable is not working properly
and will be disabled.
Troubleshooting Guide www.hp.com A–7

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
912-Computer Computer cover was No action required.
Cover Has Been removed since last system
Removed Since Last startup.
System Startup
914-Hood Lock Coil Smart Cover Lock 1. Reconnect or replace hood locking
is not Connected mechanism is missing or mechanism.
not connected.
2. Reseat or replace hood locking
mechanism cable.
916-Power Button Power button harness has Reconnect or replace power button
Not Connected been detached or harness.
unseated from
motherboard.
917-Front Audio Not Front audio harness has Reconnect or replace front audio harness.
Connected been detached or
unseated from
motherboard.
918-Front USB Not Front USB harness has Reconnect or replace front USB harness.
Connected been detached or
unseated from
motherboard.
919-Multi-Bay Riser Riser card has been Reinsert riser card.
not Connected removed or has not been
reinstalled properly in the
system.
1151-Serial Port A Both external and 1. Remove any serial port expansion
Address Conflict internal serial ports are cards.
Detected assigned to COM1.
2. Clear CMOS. (See Appendix B,
“Password Security and Resetting
CMOS.”)
3. Reconfigure card resources and/or
run Computer Setup or Windows
utilities.
A–8 www.hp.com Troubleshooting Guide

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
1152-Serial Port B Both external and 1. Remove any serial port expansion
Address Conflict internal serial ports are cards.
Detected assigned to COM2.
2. Clear CMOS. (See Appendix B,
“Password Security and Resetting
CMOS.”)
3. Reconfigure card resources and/or
run Computer Setup or Windows
utilities.
1155-Serial Port Both external and 1. Remove any serial port expansion
Address Conflict internal serial ports are cards.
Detected assigned to same IRQ.
2. Clear CMOS. (See Appendix B,
“Password Security and Resetting
CMOS.”)
3. Reconfigure card resources and/or
run Computer Setup or Windows
utilities.
1201-System Audio Device IRQ address Enter Computer Setup and reset the IRQ in
Address Conflict conflicts with another Advanced > Onboard Devices.
Detected device.
1202-MIDI Port Device IRQ address Enter Computer Setup and reset the IRQ in
Address Conflict conflicts with another Advanced > Onboard Devices.
Detected device.
1203-Game Port Device IRQ address Enter Computer Setup and reset the IRQ in
Address Conflict conflicts with another Advanced > Onboard Devices.
Detected device.
Troubleshooting Guide www.hp.com A–9

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
1720-SMART Hard Hard drive is about 1. Determine if hard drive is giving
Drive Detects to fail. (Some hard drives correct error message. Enter
Imminent Failure have a hard drive Computer Setup and run the Drive
firmware patch that will Protection System test under
fix an erroneous error Storage > DPS Self-test.
message.)
2. Apply hard drive firmware patch
if applicable. (Available at
www.hp.com/support.)
3. Back up contents and replace hard
drive.
1785-Multibay (for Multibay option/ 1. Ensure the Multibay option is
incorrectly installed non-USDT systems) attached as device 0 on the IDE
cable.
1. Multibay option
ribbon cables not 2. Ensure no other device is attached to
seated or improperly the same IDE cable.
attached.
3. Ensure both ends of the IDE and
2. Multibay device not Multibay ribbon cables are properly
properly seated. seated.
3. Multibay diskette 4. Ensure the Multibay device is fully
present. inserted.
5. Ensure a Multibay diskette is not
present (Multibay diskette drives are
not supported by the Multibay
option).
(for integrated Multibay/ 1. Ensure the Multibay device is fully
USDT systems) inserted.
1. Multibay device not 2. Ensure the Multibay riser is properly
properly seated. seated.
2. Multibay riser not
properly seated.
A–10 www.hp.com Troubleshooting Guide

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
1794-Inaccessible A device is attached to 1. If using Windows 2000 or Windows
devices attached to SATA 1 and/or SATA 3. XP, change “SATA Emulation” to
SATA 1 and/or Devices attached to these “Separate IDE Controller” in
SATA 3 connectors will be Computer Setup.
inaccessible while “SATA
(for systems with 4 2. If not using Windows 2000 or
Emulation” is set to
SATA ports) Windows XP, relocate the affected
“Combined IDE
devices to SATA 0 or SATA 2 (if
Controller” in Computer
available).
Setup.
3. Remove the affected devices from
SATA 1 and SATA 3.
1794-Inaccessible A device is attached to 1. If using Windows 2000 or Windows
device attached to SATA 1. Any device XP, change “SATA Emulation” to
SATA 1 attached to this “Separate IDE Controller” in
connector will be Computer Setup.
(for systems with 2
inaccessible while “SATA
SATA ports) 2. If not using Windows 2000 or
Emulation” is set to
Windows XP, relocate the affected
“Combined IDE
device to SATA 0 (if available).
Controller” in Computer
3. Remove the affected device from
Setup.
SATA 1.
1796-SATA Cabling One or more SATA Ensure SATA connectors are used in
Error devices are improperly ascending order. For one device, use
attached. For optimal SATA 0. For two devices, use SATA 0 and
performance, the SATA 0 SATA 1. For three devices, use SATA 0,
and SATA 1 connectors SATA1, and SATA 2.
must be used before
SATA 2 and SATA 3.
1800-Temperature Internal temperature 1. Check that computer air vents are not
Alert exceeds specification. blocked and the processor cooling
fan is running.
2. Verify processor speed selection.
3. Replace the processor.
4. Replace the system board.
Troubleshooting Guide www.hp.com A–11

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
1801-Microcode Processor is not 1. Upgrade BIOS to proper version.
Patch Error supported by
2. Change the processor.
ROM BIOS.
1998-Master Boot The previously saved Run Computer Setup and save the MBR of
Record has copy of the MBR has the current bootable disk.
been Lost been corrupted.
1999-Master Boot The current MBR does not Use extreme caution. The MBR may have
Record has match the previously been updated due to normal disk
Changed saved copy of the MBR. maintenance activities (disk manager,
fdisk, or format).
Ä
Replacing the previously saved MBR
in such situations can cause data
loss.
If you are certain the MBR change is
unintentional and undesired (e.g. due to a
virus), then run Computer Setup and
restore the previously saved MBR copy.
Otherwise, run Computer Setup and either
disable MBR security or save the MBR of
the current bootable disk.
2000-Master Boot The current bootable Run Computer Setup and either disable
Record Hard Drive hard drive is not the MBR security or save the MBR of the
has Changed same as the one that was current bootable disk.
present when MBR
Security was enabled.
Invalid Electronic Electronic serial number 1. Run Computer Setup. If Setup already
Serial Number has become corrupted. has data in the field or will not allow
the serial number to be entered,
download from www.hp.com and run
SP5572.EXE (SNZERO.EXE).
2. Run Computer Setup and try to enter
serial number under Security, System
ID, then save changes.
A–12 www.hp.com Troubleshooting Guide

POST Error Messages
Numeric Codes and Text Messages (Continued)
Code/Message Probable Cause Recommended Action
Network Server Keyboard failure while 1. Reconnect keyboard with computer
Mode Active and Network Server Mode turned off.
No Keyboard enabled.
2. Check connector for bent or missing
Attached
pins.
3. Ensure that none of the keys are
depressed.
4. Replace keyboard.
Parity Check 2 Parity RAM failure. Run Computer Setup and Diagnostic
utilities.
System will not boot CPU fan not installed or 1. Open hood, press the Power button,
without fan disconnected in VSFF and see if the processor fan spins. If
chassis. the processor fan is not spinning,
make sure the fan's cable is plugged
onto the system board header. Ensure
the fan is fully/properly seated or
installed.
2. If the fan is plugged in and seated
properly, but is not spinning, then
replace the processor fan.
Troubleshooting Guide www.hp.com A–13

POST Error Messages
POST Diagnostic Front Panel LEDs and
Audible Codes
This section covers the front panel LED codes as well as the audible
codes that may occur before or during POST that do not necessarily
have an error code or text message associated with them.
✎
If you see flashing LEDs on a PS/2 keyboard, look for flashing LEDs
on the front panel of the computer and refer to the following table to
determine the front panel LED codes.
✎
Recommended actions in the following table are listed in the order in
which they should be performed.
Diagnostic Front Panel LEDs and Audible Codes
Activity Beeps Possible Cause Recommended Action
Green Power LED None Computer on. None
On.
Green Power LED None Computer in None required. Press any key or move
flashes every two Suspend to RAM the mouse to wake the computer.
seconds. mode (select
models only) or
normal Suspend
mode.
A–14 www.hp.com Troubleshooting Guide

POST Error Messages
Diagnostic Front Panel LEDs and Audible Codes (Continued)
Activity Beeps Possible Cause Recommended Action
Red Power LED 2 Processor thermal 1. Ensure that the computer air vents
flashes two times, protection are not blocked and the processor
once every second, activated: cooling fan is running.
followed by a two A fan may be 2. Open hood, press power button,
second pause. blocked or not and see if the processor fan spins. If
turning. the processor fan is not spinning,
OR make sure the fan's cable is
plugged onto the system board
The heatsink/fan
header. Ensure the fan is
assembly is not
fully/properly seated or installed.
properly attached
to the processor. 3. If fan is plugged in and seated
properly, but is not spinning, then
replace processor fan.
4. Reseat processor heatsink and
verify that the fan assembly is
properly attached.
5. Contact an authorized reseller or
service provider.
Red Power LED 3 Processor not 1. Check to see that the processor is
flashes three times, installed (not an present.
once every second, indicator of bad
2. Reseat the processor.
followed by a two processor).
second pause.
Troubleshooting Guide www.hp.com A–15

POST Error Messages
Diagnostic Front Panel LEDs and Audible Codes (Continued)
Activity Beeps Possible Cause Recommended Action
Red Power LED 4 Power failure 1. Open the hood and ensure the
flashes four times, (power supply is 4-wire power supply cable is
once every second, overloaded). seated into the connector on the
followed by a two system board.
second pause.
2. Check if a device is causing the
problem by removing ALL attached
devices (such as hard, diskette, or
optical drives, and expansion
cards). Power on the system. If the
system enters the POST, then power
off and replace one device at a
time and repeat this procedure until
failure occurs. Replace the device
that is causing the failure. Continue
adding devices one at a time to
ensure all devices are functioning
properly.
3. Replace the power supply.
4. Replace the system board.
Red Power LED 5 Pre-video memory 1. Reseat DIMMs. Power on the
flashes five times, error. system.
once every second,
2. Replace DIMMs one at a time to
followed by a two
isolate the faulty module.
second pause.
3. Replace third-party memory with
HP memory.
4. Replace the system board.
Red Power LED 6 Pre-video graphics For systems with a graphics card:
flashes six times, error.
1. Reseat the graphics card. Power on
once every second,
the system.
followed by a two
2. Replace the graphics card.
second pause.
3. Replace the system board.
For systems with integrated graphics,
replace the system board.
A–16 www.hp.com Troubleshooting Guide

POST Error Messages
Diagnostic Front Panel LEDs and Audible Codes (Continued)
Activity Beeps Possible Cause Recommended Action
Red Power LED 7 System board Replace the system board.
flashes seven times, failure (ROM
once every second, detected failure
followed by a two prior to video).
second pause.
Red Power LED 8 Invalid ROM 1. Reflash the ROM using a ROMPaq
flashes eight times, based on bad diskette. See the “ROM Flash”
once every second, checksum. section of the Desktop
followed by a two Management Guide on the
second pause. Documentation CD.
2. Replace the system board.
Red Power LED 9 System powers on 1. Check that the voltage selector,
flashes nine times, but is unable to located on the rear of the power
once every second, boot. supply (some models), is set to the
followed by a two appropriate voltage. Proper voltage
second pause. setting depends on your region.
2. Replace the system board.
3. Replace the processor.
Red Power LED 10 Bad option card. 1. Check each graphics card by
flashes ten times, removing the card (one at a time if
once every second, multiple cards), then power on the
followed by a two system to see if fault goes away.
second pause.
2. Once a bad card is identified,
remove and replace the bad option
card.
3. Replace the system board.
Troubleshooting Guide www.hp.com A–17

POST Error Messages
Diagnostic Front Panel LEDs and Audible Codes (Continued)
Activity Beeps Possible Cause Recommended Action
System does not None System unable to Press and hold the power button for less
power on and LEDs power on. than 4 seconds. If the hard drive LED
are not flashing. turns green, then:
1. Check that the voltage selector,
located on the rear of the power
supply, is set to the appropriate
voltage. Proper voltage setting
depends on your region.
2. Remove the expansion cards one at
a time until the 3V_aux light on the
system board turns on.
3. Replace the system board.
OR
Press and hold the power button for less
than 4 seconds. If the hard drive LED
does not turn on green then:
1. Check that the unit is plugged into
a working AC outlet.
2. Open hood and check that the
power button harness is properly
connected to the system board.
3. Check that both power supply
cables are properly connected to
the system board.
4. Check to see if the 3V_aux light on
the system board is turned on. If it
is turned on, then replace the
power button harness.
5. If the 3V_aux light on the system
board is not turned on, then
replace the power supply.
6. Replace the system board.
A–18 www.hp.com Troubleshooting Guide
