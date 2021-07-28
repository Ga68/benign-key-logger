# benign-key-logger

**A simple, transparent, open-source key logger, written in Python, for tracking your own key-usage statistics, originally intended for keyboard layout optimization.**

## Background

I started looking into mechanical keyboards and the variation in layouts—QWERTY, AZERTY, Colemak, Dvorak, etc.—is just the beginning. You can very rapidly descend into fascination/madness with layers, hotkeys, tap-mods, and more, especially as you get down from full-size (100+ keys) boards to the smaller ones (like 36-key boards, and sometimes even less). All of this is based on making your typing optimal, comfortable, fast, and maybe a few other personally important adjectives.

One key input to these choices though is knowing what keys and combos I really use most often. A key-logger is a really convenient way to self-analyze and see what your key-usage looks like in practice. Across people, I imagine it could vary greatly depending on what language you work in, whether you're a programmer, author, etc. However, when I tried to find a key logger for this purpose, most of what I found was tagged with headlines like "get credit card info..." or "catch your cheating girlfriend". Moreover, and perhaps more importantly, they were either closed-source executables or too complicated to understand. I'm curious about my typing, but not enough to take even a small risk of putting an actually-nefarious key-logger on my system.

## Goals

Make a key logger simple enough that a moderately experienced programmer can quickly read-through, understand, and be convinced that nothing nefarious is going on.

Use known libraries, and use as few as possible.

Keep all data local and simply consolidated. Send nothing, anywhere, off the computer.

Comment the code extensively to explain not only what's happening, but additionally the thinking behind each choice.

## Design Considerations 

### Comments

The code is **heavily** commented; perhaps excessively so. In fact, the code looks long, but it's mostly `# comments`. (At the moment that I'm writing this, the actual code is a little less than half the lines in the program.) This is in the spirit of transparency and being *benign*. I want to make sure that every decision in the code is clear, both in what it does and why it's there.

### OS & Language

I use this on my Mac, running on Python3 (3.8.1, but I presume any Python3 version would work), and haven't tested or tried it on any other operating system. I presume it would work there, but I'd also be unsurprised to find that there are intricacies that I haven't thought of. If anyone else tries it and finds ways to improve/extend it, that'd be great.

### Output Storage

There are two ways to store the output (the key-log). In both cases, it's simply put in a single file in the same directory you're running the script from.

1. Put every key-press into a text file, one per line
2. Put every key-press into a [SQLite](https://sqlite.org/index.html) database

[SQLite](https://sqlite.org/index.html) is on by default, and text-file logging is off. You can swap that, turn both on if you wish, but both off would be an odd choice.

I chose [SQLite](https://sqlite.org/index.html) because it entirely resides in a single file that you can delete anytime you want, and it doesn't require any separate database engine. If you're not familiar with it, it's effectively just like putting your data in a text file, one entry per line, but it does it in a structured way that, when you use a program that knows how to read that structure, gives you much of the power of SQL. The nice thing is that 100% of the data, meta-data, etc. is all in that one file. And having the entries in a database, does provide some advantages (if you know SQL) when you want to quickly answer questions like "Show me the keys I press in descending order, by frequency?" or "What percentage of key presses is the spacebar?" You can even do some fun stuff like "How fast do I type?" (since timestamps are maintained in the SQLite log), "Do I type more during odd or even hours of the day?", and other, life-changing questions-and-answers.

I use a [DB Browser for SQLite](https://sqlitebrowser.org/) to look at and query the SQLite datafile.

### Logging

The Python logging module is used to provide INFO, DEBUG, WARNING, etc. messages. As written, this goes to the screen, not to a file anywhere. So if you run this from the terminal, you'll see a stream of key-presses rolling on by. If you wanted it in a file, I guess you could; however, given the goal of trying to stay benign, I decided the screen made more sense to keep that information "ephemeral". By default it's written to only show INFO (and above) messages—no DEBUG information—but you can change that and enjoy the far more copious entries screaming on down your output window, if that's your thing.

## Usage

### Security Permissions

<img src="https://gleadee-public-us-east-1.s3.amazonaws.com/github/benign-key-logger/security_and_privacy.png" width="350" align="right" />
I only know how (and even if you need) to grant keyboard access on a Mac. You must give the script Accessibility permissions in `System Preferences > Security & Privacy > Privacy > Accesibility`. (Don't forget you likely need to unlock this preferences screen to make any changes.) This gives the app you run it from permission to see the keyboard events. I usually use Terminal, but you can also run it from your code editor, like Sublime Text. Without this step, the script will just sit there silently, deaf to all keyboard events. The macOS automatically supresses logging when it switches into secure input mode (passwords). So, through not effort of my own, it very nicely avoids logging any information typed into OS-labeled password screens. At least for me, this is even true for password fields in my browser. Nice!

### Dependencies

You'll need to install `pynput`. You can see more details on that library from [PyPi](https://pypi.org/project/pynput/) or [GitHub](https://github.com/moses-palmer/pynput), and you can read [its documentation](https://pynput.readthedocs.io/en/latest/) as well. The other items are all Python-standard libraries: `datetime`, `logging`, and `sqlite3`. I purposefully don't install `pynput` locally here because I don't want you to have to trust that the version included hasn't been tampered with. So, you can add it in to your system, or locally to the folder, using `pip`: `pip3 install pynput`.

### Running It

I run it from the Terminal with `python3 key_logger.py`. One could add execution permissions to the file (`chmod +x key_logger.py`) and then run it like a script (`./key_logger.py`), since it does have the Python shebang at the top; however, in the spirit of being *benign*, I don't like the idea of making the file executable, even though I know it's not an EXE, but ¯\\\_(ツ)\_/¯.
