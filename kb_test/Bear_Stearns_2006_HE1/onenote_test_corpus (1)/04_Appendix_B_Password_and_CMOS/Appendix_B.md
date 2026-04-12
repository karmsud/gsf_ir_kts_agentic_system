# Appendix B — Password Security and Resetting CMOS

B
Password Security and Resetting CMOS
This computer supports security password features, which can be
established through the Computer Setup Utilities menu.
This computer supports two security password features that are
established through the Computer Setup Utilities menu: setup
password and power-on password. When you establish only a setup
password, any user can access all the information on the computer
except Computer Setup. When you establish only a power-on
password, the power-on password is required to access Computer
Setup and any other information on the computer. When you establish
both passwords, only the setup password will give you access to
Computer Setup.
When both passwords are set, the setup password can also be used
in place of the power-on password as an override to log in to the
computer. This is a useful feature for a network administrator.
If you forget the password for the computer, there are two methods
for clearing that password so you can gain access to the information
on the computer:
■ Resetting the password jumper
■ Using the Clear CMOS button
Ä
CAUTION: Pushing the CMOS button will reset CMOS values to factory
defaults and will erase any customized information including passwords,
asset numbers, and special settings. It is important to back up the
computer CMOS settings before resetting them in case they are needed
later. Back up is easily done through Computer Setup. See the Computer
Setup (F10) Utility Guide on the Documentation CD for information on
backing up the CMOS settings.
Troubleshooting Guide www.hp.com B–1

Password Security and Resetting CMOS
Resetting the Password Jumper
To disable the power-on or setup password features, or to clear the
power-on or setup passwords, complete the following steps:
1. Shut down the operating system properly, then turn off the
computer and any external devices, and disconnect the power
cord from the power outlet.
2. With the power cord disconnected, press the power button again
to drain the system of any residual power.
Å
WARNING: To reduce the risk of personal injury from electrical shock
and/or hot surfaces, be sure to disconnect the power cord from the wall
outlet, and allow the internal system components to cool before touching.
Ä
CAUTION: When the computer is plugged in, the power supply always
has voltage applied to the system board even when the unit is turned off.
Failure to disconnect the power cord can result in damage to the system.
Ä
CAUTION: Static electricity can damage the electronic components
of the computer or optional equipment. Before beginning these
procedures, ensure that you are discharged of static electricity by briefly
touching a grounded metal object. See the Safety & Regulatory
Information guide on the Documentation CD for more information.
3. Remove the computer cover or access panel.
4. Locate the header and jumper.
✎
The password jumper is green so that it can be easily identified. For
assistance locating the password jumper and other system board
components, see the Illustrated Parts Map (IPM) for that particular
system. The IPM can be downloaded from www.hp.com/support.
5. Remove the jumper from pins 1 and 2. Place the jumper on either
pin 1 or 2, but not both, so that it does not get lost.
6. Replace the computer cover or access panel.
7. Reconnect the external equipment.
B–2 www.hp.com Troubleshooting Guide

Password Security and Resetting CMOS
8. Plug in the computer and turn on power. Allow the operating
system to start. This clears the current passwords and disables the
password features.
9. To establish new passwords, repeat steps 1 through 4, replace the
password jumper on pins 1 and 2, then repeat steps 6 through 8.
Establish the new passwords in Computer Setup. Refer to the
Computer Setup (F10) Utility Guide on the Documentation CD
for Computer Setup instructions.
Clearing and Resetting the CMOS
The computer’s configuration memory (CMOS) stores password
information and information about the computer’s configuration.
Using the CMOS Button
1. Turn off the computer and any external devices, and disconnect
the power cord from the power outlet.
2. Disconnect the keyboard, monitor, and any other external
equipment connected to the computer.
Å
WARNING: To reduce the risk of personal injury from electrical shock
and/or hot surfaces, be sure to disconnect the power cord from the wall
outlet, and allow the internal system components to cool before touching.
Ä
CAUTION: When the computer is plugged in, the power supply always
has voltage applied to the system board even when the unit is turned off.
Failure to disconnect the power cord can result in damage to the system.
Ä
CAUTION: Static electricity can damage the electronic components
of the computer or optional equipment. Before beginning these
procedures, ensure that you are discharged of static electricity by briefly
touching a grounded metal object. See the Safety & Regulatory
Information guide on the Documentation CD for more information.
Troubleshooting Guide www.hp.com B–3

Password Security and Resetting CMOS
3. Remove the computer cover or access panel.
Ä
CAUTION: Pushing the CMOS button will reset CMOS values to factory
defaults and will erase any customized information including passwords,
asset numbers, and special settings. It is important to back up the
computer CMOS settings before resetting them in case they are needed
later. Back up is easily done through Computer Setup. See the Computer
Setup (F10) Utility Guide on the Documentation CD for information on
backing up the CMOS settings.
4. Locate, press, and hold the CMOS button in for five seconds.
✎
Make sure you have disconnected the AC power cord from the wall
outlet. The CMOS button will not clear CMOS if the power cord is
connected.
CMOS button
✎
For assistance locating the CMOS button and other system board
components, see the Illustrated Parts Map (IPM) for that particular
system.
5. Replace the computer cover or access panel.
B–4 www.hp.com Troubleshooting Guide

Password Security and Resetting CMOS
6. Reconnect the external devices.
7. Plug in the computer and turn on power.
✎
You will receive POST error messages after clearing CMOS and
rebooting advising you that configuration changes have occurred. Use
Computer Setup to reset your passwords and any special system
setups along with the date and time.
See the Desktop Management Guide on the Documentation CD for
further instructions on reestablishing passwords. For instructions on
Computer Setup, see the Computer Setup (F10) Utility Guide on the
Documentation CD.
Using Computer Setup to Reset CMOS
To reset CMOS through Computer Setup, you must first access the
Computer Setup Utilities menu.
When the Computer Setup message appears in the lower-right corner
of the screen, press the F10 key. Press Enter to bypass the title
screen, if necessary.
✎
If you do not press the F10 key while the message is displayed, you
must turn the computer off, then on again, to access the utility.
A choice of five headings appears in the Computer Setup Utilities
menu: File, Storage, Security, Power, and Advanced.
To reset CMOS to the factory default settings first set time and date,
then use the arrow keys or the Tab key to select File > Set Defaults
and Exit. This resets the soft settings that include boot sequence
order and other factory settings. It will not, however, force hardware
rediscovery.
See the Desktop Management Guide on the Documentation CD for
further instructions on reestablishing passwords. For instructions on
Computer Setup, see the Computer Setup (F10) Utility Guide on the
Documentation CD.
Troubleshooting Guide www.hp.com B–5

Password Security and Resetting CMOS
B–6 www.hp.com Troubleshooting Guide
