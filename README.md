# benign-key-logger

**A simple, transparent, open-source key logger, written in Python, for tracking your own key usage, originally intended as a tool for keyboard layout optimization.**

## Background

I started looking into mechanical keyboards and the variation in layouts—QWERTY, AZERTY, Colemak, Dvorak, etc.—is just the beginning. You can very rapidly descend into fascination/madness with layers, hotkeys, tap-mods, and more, especially as you get down from full-size (100+ keys) boards to the smaller ones (like 36-key boards, and sometimes even less). All of this is based on making your typing optimal, comfortable, fast, and maybe a few other personally important adjectives.

One key input to these choices is knowing what keys and combos you really use most often. A key logger is a convenient way to self-analyze and see what your key usage looks like in practice. (As opposed to simply analyzing language averages, or short samples of work.) Across people, it could vary greatly depending on what language you work in (English, Swedish, Portuguese), and whether you're a programmer, author, etc. So, when I tried to find a key logger for this purpose, most of what I found was tagged with headlines like "get credit card info..." or "catch your cheating girlfriend". Moreover, and perhaps more importantly, they were either closed-source, executable files, or too complicated to understand. (I'm curious about my typing, but not enough to take even a small risk of putting an actually nefarious key logger on my system!)

## Goals

Make a key logger simple enough that a moderately experienced programmer can quickly read through, understand, and be convinced that nothing nefarious is going on.

Use standard and/or known libraries, and use as few as possible.

Keep all data local and simply consolidated. Send nothing, anywhere, off the computer.

Comment the code extensively to explain not only what's happening, but additionally the thinking behind each choice.

## Design Considerations 

### Comments

The code is **heavily** commented; perhaps excessively so. In fact, the code looks long, but it's mostly `# comments`. (At the moment that I'm writing this, the actual code is a little less than half the lines in the program.) This is in the spirit of transparency and being *benign*. I want to make sure that every decision in the code is clear, both in what it does and why it's there.

### OS & Language

I use this on my Mac, running on Python3 (3.8.1, but I presume any Python3 version would work), and haven't tried it on any other operating system. I presume it would work, but it seems easy to believe that there are details that I don't know of. If anyone tries it and finds ways to improve/extend it, that'd be great.

### Output Storage

There are two ways to store the output (the key log). In both cases, it's put in a single file in the same directory you're running the script.

1. Put every key stroke into a text file, one entry per line
2. Put every key stroke into a [SQLite](https://sqlite.org/index.html) database

[SQLite](https://sqlite.org/index.html) is the default option. You can swap that or turn both on if you wish, but both *off* would be an odd choice.

I chose [SQLite](https://sqlite.org/index.html) because the output is a single file that you can delete anytime you want, and it doesn't require any separate database engine. If you're not familiar with it, it's much like putting your data in a text file, one entry per line, but it does so in a structured way that, when you use a program that knows how to read that structure, gives you the power of SQL. The nice thing is that 100% of the data, meta data, etc. is in that one file. And having the entries in a database, does provide some advantages (if you know SQL) when you want to answer questions like "Show me the keys I press in descending order, by frequency?" or "What percentage of key strokes is the space bar?" You can even do some fun stuff like "How fast do I type?" (since timestamps are maintained in the SQLite log), "Do I type more during odd or even hours of the day?", and other, life changing questions-and-answers. A basic version of this is built into the SQLite output file, in the form of predefined views.

Among other options, two applications I use to look at and query the SQLite data file are
- [SQLiteStudio](https://sqlitestudio.pl/)
- [DB Browser for SQLite](https://sqlitebrowser.org/)

### Logging

The Python logging module is used to provide INFO, DEBUG, WARNING, etc. messages. As written, this goes to the screen, not to a file. So if you run this from the terminal, you'll see a stream of key strokes rolling on by. If you want it in a file, you could; however, given the goal of trying to stay benign, I decided the screen made more sense to keep that information "ephemeral". By default it's written to show only INFO (and above) messages—no DEBUG information—but you can change that and enjoy the copious DEBUG entries screaming on down your output window, if that's your thing.

## Usage

### Security Permissions

<img src="https://gleadee-public-us-east-1.s3.amazonaws.com/github/benign-key-logger/security_and_privacy.png" width="350" align="right" />

I only know how (and even if you need) to grant keyboard access on a Mac. You must give the script Accessibility permissions in `System Preferences > Security & Privacy > Privacy > Accessibility`. (Don't forget that you likely need to unlock this Preferences screen to make any changes.) This gives the app you run it from permission to see the keyboard events. I usually use the Terminal, but you can also run it from your code editor. Without this step, the script will just sit there silently, deaf to all keyboard events. macOS automatically suppresses logging when it switches into Secure Input Mode (passwords). So, through no effort of my own, it very nicely avoids logging any information typed into OS-labeled password text boxes. At least for me, this is even true for password fields in my browser. Nice! (I don't know if Windows or Linux has anything comparable, so if you use it there, be aware that your passwords may or may not be tracked by the logger.)

### Dependencies

You'll need to install `pynput`. You can see more details on that library from [PyPi](https://pypi.org/project/pynput/) or [GitHub](https://github.com/moses-palmer/pynput), and you can read [its documentation](https://pynput.readthedocs.io/en/latest/) as well. The other items are all Python-standard libraries: `datetime`, `logging`, and `sqlite3`. I purposefully do not put `pynput` here in this repo because I don't want you to have to trust that the version included hasn't been tampered with. You can use `pip` to install it: `pip3 install pynput`.

### Running It

I run it from the Terminal with `python3 key_logger.py`. You could add execution permissions to the file (`chmod +x key_logger.py`) and then run it like a script (`./key_logger.py`), since it does have the Python shebang at the top; however, in the spirit of being *benign*, I don't like the idea of making the file executable, even though I know it's not an EXE, but ¯\\\_(ツ)\_/¯.

## Screenshots

<img src="https://gleadee-public-us-east-1.s3.amazonaws.com/github/benign-key-logger/screenshot_terminal.jpg" width="500" />&nbsp;<img src="https://gleadee-public-us-east-1.s3.amazonaws.com/github/benign-key-logger/screenshot_sqlite_key_log.jpg" width="500" />&nbsp;<img src="https://gleadee-public-us-east-1.s3.amazonaws.com/github/benign-key-logger/screenshot_sqlite_key_counts.jpg" width="500" />
