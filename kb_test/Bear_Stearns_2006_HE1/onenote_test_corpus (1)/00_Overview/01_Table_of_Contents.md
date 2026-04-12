# Table of Contents (from PDF text extract)

Troubleshooting Guide
Business Desktops
Document Part Number: 361204-001
May 2004
This guide provides helpful hints and solutions for troubleshooting
the above products as well as scenarios for possible hardware and
software problems.

© Copyright 2004 Hewlett-Packard Development Company, L.P.
The information contained herein is subject to change without notice.
Microsoft, MS-DOS, Windows, and Windows NT are trademarks of Microsoft
Corporation in the U.S. and other countries.
The only warranties for HP products and services are set forth in the express
warranty statements accompanying such products and services. Nothing herein
should be construed as constituting an additional warranty. HP shall not be liable
for technical or editorial errors or omissions contained herein.
This document contains proprietary information that is protected by copyright.
No part of this document may be photocopied, reproduced, or translated to
another language without the prior written consent of Hewlett-Packard
Company.
Å
WARNING: Text set off in this manner indicates that failure to follow
directions could result in bodily harm or loss of life.
Ä
CAUTION: Text set off in this manner indicates that failure to follow
directions could result in damage to equipment or loss of information.
Troubleshooting Guide
Business Desktops
First Edition (May 2004)
Document Part Number: 361204-001

Contents
1 Computer Diagnostic Features
Diagnostics for Windows . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1–1
Detecting Diagnostics for Windows. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1–2
Installing Diagnostics for Windows. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1–3
Using Categories in Diagnostics for Windows. . . . . . . . . . . . . . . . . . . . . . . . . . . . 1–4
Running Diagnostic Tests in Diagnostics for Windows. . . . . . . . . . . . . . . . . . . . . 1–6
Configuration Record . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1–9
Installing Configuration Record. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1–10
Running Configuration Record. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1–10
Protecting the Software. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1–11
Restoring the Software . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1–11
2 Troubleshooting Without Diagnostics
Safety and Comfort. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–1
Before You Call for Technical Support . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–2
Helpful Hints. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–4
Solving General Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–6
Solving Power Supply Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–10
Solving Diskette Problems . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–12
Solving Hard Drive Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–15
Solving MultiBay Problems . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–18
Solving Display Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–19
Solving Audio Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–24
Solving Printer Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–27
Solving Keyboard and Mouse Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–28
Solving Hardware Installation Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–30
Solving Network Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–33
Solving Memory Problems . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–37
Solving Processor Problems . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–38
Troubleshooting Guide www.hp.com iii

Contents
Solving CD-ROM and DVD Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–39
Solving Drive Key Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–41
Solving Internet Access Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–41
Solving Software Problems. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–44
Contacting Customer Support. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2–45
A POST Error Messages
POST Numeric Codes and Text Messages . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A–2
POST Diagnostic Front Panel LEDs and Audible Codes. . . . . . . . . . . . . . . . . . . . . . A–14
B Password Security and Resetting CMOS
Resetting the Password Jumper. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . B–2
Clearing and Resetting the CMOS . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . B–3
Using the CMOS Button. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . B–3
Using Computer Setup to Reset CMOS. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . B–5
C Drive Protection System (DPS)
Accessing DPS Through Diagnostics for Windows . . . . . . . . . . . . . . . . . . . . . . . . . . . C–2
Accessing DPS Through Computer Setup . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . C–3
D Setting up Analog/Digital Audio Output
Index
iv www.hp.com Troubleshooting Guide
