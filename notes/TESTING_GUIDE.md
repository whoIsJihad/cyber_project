# Testing This SYN Packet Project: a Beginner Guide

This guide explains what our tests are, why they exist, how to run them, and how to understand failures. It is written for this project, not as a generic Python lecture.

At the moment, our code builds packet bytes locally. It does **not** send network traffic yet. The tests check whether those local bytes are correct before we ever place them on the isolated network.

## 1. The shortest possible explanation

A test is a small Python function that asks one precise question about our code.

For example:

> When we build a basic TCP SYN header, is it exactly 20 bytes long?

The code asks that question like this:

```python
assert len(header) == 20
```

`assert` means “this must be true.”

- If it is true, the test passes.
- If it is false, the test fails and Python shows what it received instead.

A testing framework is a tool that finds all these small test functions, runs them, and gives us one result summary.

This project uses **pytest**.

## 2. What is pytest?

`pytest` is a Python testing framework. We did not write it. It is an installed tool that does four useful jobs:

1. Finds files whose names begin with `test_` inside `tests/`.
2. Finds functions whose names begin with `test_`.
3. Runs each of those functions.
4. Reports whether each test passed or failed.

We run it from the **main project folder**, which is:

```text
/mnt/Data/4-1/syn-flood-dos-project
```

Use this command:

```bash
python3 -m pytest -q
```

Meaning:

- `python3` starts Python.
- `-m pytest` tells that Python installation to run its installed pytest tool.
- `-q` means “quiet”: show a compact result instead of extra detail.

When every current test passes, the result looks like this:

```text
....................                                                     [100%]
20 passed
```

Every dot is one passing test. Twenty dots means twenty separate questions were answered correctly. Always run the command yourself rather than relying on an older result written in this guide.

## 3. Why use `python3 -m pytest` instead of only `pytest`?

Your computer can have more than one Python installation. `python3 -m pytest` means:

> Use the pytest connected to this exact `python3`.

That avoids a common beginner problem where one command uses Python A while another command uses Python B and cannot find the same packages.

## 4. What exactly are we testing right now?

We are **not** testing whether the receiver VM is attacked. We are not testing Nginx. We are not testing Ethernet or the real network.

We are testing whether our local packet-building code makes the bytes we intend.

```text
checksum.py  → calculate a checksum correctly
tcp.py       → place TCP fields in correct byte positions
ipv4.py      → place IPv4 fields in correct byte positions
packet.py    → join IPv4 + TCP into one 40-byte packet
dry_run.py   → display that packet without sending it
```

This matters because a raw packet with one wrong byte may be ignored by the receiver. If we begin by sending packets, it is hard to tell whether a failure comes from networking, permissions, an invalid checksum, or a wrong field. Local tests remove the byte-level uncertainty first.

## 5. The project layout

```text
client/                  Our real code
  checksum.py            Internet checksum
  tcp.py                 TCP header and TCP checksum
  ipv4.py                IPv4 header and IPv4 checksum
  packet.py              IPv4 + TCP packet assembler
  dry_run.py             Print packet bytes; never send

tests/                   Questions that check the real code
  test_checksum.py
  test_tcp.py
  test_ipv4.py
  test_packet.py
  test_dry_run.py
```

The important rule is:

```text
client/ = implementation
tests/  = proof checks for the implementation
```

Do not put the real packet-building logic inside `tests/`. Tests should call the real code, then examine its result.

## 6. How to read one simple test

Open `tests/test_checksum.py` and look at this test:

```python
def test_one_complete_16_bit_word() -> None:
    assert internet_checksum(b"\x00\x01") == 0xFFFE
```

Read it as a sentence:

> When `internet_checksum` receives the two bytes `00 01`, its answer must be `FFFE`.

The three pieces are:

```python
internet_checksum(b"\x00\x01")   # run our real function
==                              # compare its answer
0xFFFE                          # expected answer
```

The expected answer was chosen from the checksum rule, not copied from the function while it runs.

## 7. The usual test shape: arrange, act, assert

Most tests have three small steps.

```python
def test_example() -> None:
    # Arrange: choose known input.
    header = build_tcp_syn_header(
        source_port=0x3039,
        destination_port=0x0050,
        sequence_number=0x11223344,
        window_size=0x4000,
    )

    # Act: the function already ran and returned header.

    # Assert: inspect one exact result.
    assert header[2:4] == b"\x00\x50"
```

For the packet project, “arrange” means choosing visible fixed test values. “Act” means calling the function. “Assert” means checking the resulting bytes.

## 8. What each current test file proves

### `tests/test_checksum.py`

This file checks the smallest checksum cases first.

| Test question | Why it matters |
|---|---|
| What is the checksum of no data? | Checks the starting result. |
| What happens for one complete two-byte word? | Checks normal addition and inversion. |
| What happens for an odd number of bytes? | Checks the required zero byte used only for checksum calculation. |
| What happens when a word is `FFFF`? | Checks carry/wrap behavior. |

These are unit tests. A unit test checks one small function without a VM or network.

### `tests/test_tcp.py`

This file checks the 20-byte bare TCP SYN header.

| Test question | Expected result |
|---|---|
| Is the base TCP header 20 bytes? | Yes. |
| Are ports in bytes 0–3? | Source `30 39`; destination `00 50`. |
| Are sequence and acknowledgement fields in the right positions? | Sequence `11 22 33 44`; acknowledgement all zero. |
| Are header length and SYN flag correct? | Byte 12 is `50`; byte 13 is `02`. |
| Are the window, temporary checksum, and urgent pointer correct? | `40 00`, then zero checksum and zero urgent pointer. |
| Is the pseudo-header exactly correct? | It has the two IPs, `00`, `06`, and `00 14`. |
| Does the completed TCP checksum validate? | Recalculation returns `0000`. |

### `tests/test_ipv4.py`

This file checks the 20-byte IPv4 header.

| Test question | Expected result |
|---|---|
| Is the IPv4 header 20 bytes? | Yes, because we have no IPv4 options. |
| Are version, IHL, and total length correct? | `45 00 00 28`. |
| Are identification, fragment values, TTL, and protocol correct? | `12 34 00 00 40 06`. |
| Are addresses and checksum correct? | The test addresses are present and checksum validation returns `0000`. |
| Does TTL fit in one byte? | `0x100` must be rejected. |

### `tests/test_packet.py`

This file checks that the separate pieces become one real packet layout.

```text
bytes 0–19   = IPv4 header
bytes 20–39  = TCP header
total        = 40 bytes
```

It checks the entire expected packet bytes, not only the length. It also rechecks both the IPv4 and TCP checksums after assembly.

### `tests/test_dry_run.py`

This file checks the text printed by the dry-run helper. It proves that the report includes packet length, starts of both headers, and the sentence saying no packet was sent.

It does not prove that a terminal window printed it beautifully. It proves that the function produced the expected text.

## 9. Test categories in plain language

You will hear these names often.

### Unit test

Checks one small piece in isolation.

Example from this project:

```text
Does `internet_checksum` return the right number for these bytes?
```

### Integration test

Checks that multiple pieces work together.

Example from this project:

```text
Does `packet.py` join a valid IPv4 header and valid TCP header into a valid 40-byte packet?
```

Our `test_packet.py` is a small local integration test. It is still offline.

### End-to-end test

Checks the real complete path.

For this project, a later end-to-end test will be something like:

```text
Sender VM sends one authorized test packet
Receiver capture shows it arrived
Capture shows the expected TCP fields
```

That is not part of the current pytest suite because it needs real VMs, network permission, and packet capture.

## 10. How to run one test file

Run only checksum tests:

```bash
python3 -m pytest -q tests/test_checksum.py
```

Run only TCP tests:

```bash
python3 -m pytest -q tests/test_tcp.py
```

Run only one named test:

```bash
python3 -m pytest -q tests/test_tcp.py::test_header_length_and_syn_flag_are_correct
```

Use this when you are changing one small function and do not want to wait through every test. Before you call the change finished, run the complete suite too.

## 11. What a failure looks like

Suppose someone accidentally changes the SYN flag from `0x02` to `0x01`. The test expects `0x02`, but receives `0x01`.

Pytest would show something like:

```text
FAILED tests/test_tcp.py::test_header_length_and_syn_flag_are_correct

E       assert 1 == 2
```

Read it in this order:

1. Read the first `FAILED` line. It tells you which question failed.
2. Read the line beginning with `assert`.
3. Compare the actual value with the expected value.
4. Open the implementation function named by the test.
5. Change the smallest relevant line.
6. Run that one test again.
7. Run the whole suite after it passes.

Do not start changing unrelated packet fields just because one assertion failed.

## 12. `pytest.raises`: testing an error on purpose

Not every good test expects success. Sometimes rejecting bad input is the correct behavior.

This project contains:

```python
with pytest.raises(ValueError, match="ttl must fit"):
    build_ipv4_header(
        source_ip=b"\xC0\xA8\x96\x0A",
        destination_ip=b"\xC0\xA8\x96\x14",
        payload_length=20,
        identification=0x1234,
        ttl=0x100,
    )
```

Read it as:

> This call must fail with a `ValueError` because `0x100` needs more than one byte.

If the call silently succeeds, the test fails. That is good: it tells us invalid IPv4 data could enter our packet builder.

## 13. Tests versus the dry run

These are different checks.

```text
pytest
  Proves selected facts automatically.
  Example: byte 13 is exactly 02.

dry run
  Lets a human inspect the full packet as hexadecimal.
  Example: you can see the 40 bytes in their real order.
```

Run the dry run from the project folder:

```bash
python3 -m client.dry_run
```

Use both. The tests catch regression mistakes. The dry run helps you understand the final result.

## 14. How to add a test when we add new code

Use this repeatable routine.

1. Say what the new function must do in one sentence.
2. Choose one fixed input that is easy to read in hexadecimal.
3. Write the expected output before looking at the function's output.
4. Add a test function to the matching `tests/test_...py` file.
5. Run the test. It should fail if the feature is not written yet.
6. Write the smallest implementation that makes it pass.
7. Add one bad-input test if the function must reject unsafe or impossible values.
8. Run the complete suite.

For example, before creating a sender function, useful local tests will ask:

```text
Does it reject a destination that is not the isolated receiver?
Does it reject a destination port other than 80?
Does it stop after its configured count or duration?
Does it report how many packets it actually sent?
```

Those tests can replace the real socket with a fake send function, so they prove our loop logic without producing traffic.

## 15. What tests cannot prove

Passing tests do **not** prove all of these things:

- the receiver VM is running;
- Nginx is active;
- the sender has permission to create a raw socket;
- the packet reaches `192.168.150.20`;
- Linux accepts or replies to the packet;
- an experiment affects the receiver;
- a packet capture looks correct.

Those need later VM checks, packet capture, and ordinary HTTP baseline measurements. Tests give us confidence that our own local packet construction is not the obvious cause of a failure.

## 16. When should you run tests?

Run the complete suite:

- before starting new work, to know the current baseline;
- after changing a function;
- before copying code to a VM;
- before claiming a coding stage is complete.

Run one test file while you are actively fixing one function. Run everything before moving to the next project stage.

## 17. A short checklist

```text
[ ] I am in /mnt/Data/4-1/syn-flood-dos-project
[ ] I ran: python3 -m pytest -q
[ ] Every test passed
[ ] I know what the changed test is checking
[ ] I ran the dry run if packet bytes changed
[ ] I have not treated local passing tests as proof that the VM experiment works
```

## 18. The one sentence to remember

> A test gives known input to our code and checks that the output matches the expected result.

For this project, we test bytes locally first so that later VM and network results are easier to trust and explain.
