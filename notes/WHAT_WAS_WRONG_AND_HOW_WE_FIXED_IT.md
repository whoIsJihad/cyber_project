# What was wrong, and how we found it

Plain language, for you. No jargon dump.

## The symptom

You ran the SYN flood lab. Attack or no attack, the website kept working
perfectly. No slowdown, no failed requests. That's suspicious — a SYN flood
lab is supposed to show the site struggling at least once (the "unprotected"
case), otherwise there's nothing to defend against.

## Bug #1 — the attack was too weak

The flood sender was a single Python process sending one packet at a time
with a tiny sleep in between. That kind of loop can't go faster than about
800-1000 packets per second, no matter what rate you ask for. That's a
trickle, not a flood, for a modern Linux box.

**Fix:** made the sender run 8 copies of itself at once (`--workers 8`), each
sending its own slice of packets. Now the total rate actually hits what you
ask for.

## Bug #2 — the "small queue" setting did nothing

The script was shrinking `net.ipv4.tcp_max_syn_backlog` (a kernel setting) to
16, thinking that would make the server's waiting-room for half-finished
connections tiny and easy to overflow.

Two problems with that, found by testing it by hand on the actual VM:

1. Changing that setting while nginx is already running doesn't do anything
   — nginx already opened its listening "door" earlier, with its own queue
   size baked in. Changing the kernel setting afterward is like changing the
   blueprint after the building is built.
2. Even worse: on this VM's kernel, that setting turns out to not really
   control the queue size at all anymore. The real limit came from nginx's
   own configuration the whole time — nginx defaults to a queue of 511,
   completely ignoring that kernel setting.

We only found this by testing directly: set the kernel value to 16, flood the
server, and check with `ss` how many half-open connections actually piled up.
It was 512, not 16. That number — 512 — was the real limit as long as we kept
trying to control it from the wrong knob.

**Fix:** edit nginx's own config file (`listen 80 ... backlog=8;`) and restart
nginx so it actually opens its door with a small queue. Checked again with
`ss` afterward — the queue really was small this time.

## Bug #3 — even a small queue wasn't enough by itself

With a genuinely small queue (tried 16, then 8, then even 1), we still saw
the website answer every request instantly at first. Because the sender and
the website are on the same fast local network, a real request finishes its
handshake in under a millisecond — so it almost always finds a free slot,
even when fake traffic is trying to fill the queue.

Only once the queue was pushed small enough (backlog = 8, with syncookies
turned off) did the timing finally tip over: fake traffic filled the queue
faster than real requests could sneak in, and the site started timing out.
That's the actual demonstration the lab needed.

## What the numbers now show

- **Protected** (SYN cookies on): flood hits, but the server survives —
  basically 100% of real requests still succeed.
- **Unprotected** (SYN cookies off, same flood, same tiny queue): most real
  requests time out. This is the actual "denial of service."

That contrast — same attack, cookies on vs off, opposite outcome — is the
whole point of the lab, and now it actually shows up in the results.

## How we found all this, in short

Not by guessing. By logging into both VMs directly and testing one variable
at a time: check the real queue size with `ss`, flood it, watch the number
change live, try `curl` requests during the flood and time them, shrink the
queue further, repeat. Every claim above was checked against what the VM
actually did, not just what the settings were supposed to do.
