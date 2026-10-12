# Authored WAV fixture

`stereo-impulses.wav` is generated solely by `make_fixture.py`, with no acquired,
private or licensed audio. It contains 16,000 PCM signed 16-bit stereo frames at
8,000 Hz. Channels are zero-based. All samples are zero except:

| Frame | Channel 0 | Channel 1 |
| --- | --- | --- |
| 0 | 16384 | 0 |
| 4000 | 0 | 24576 |
| 8000 | -16384 | 0 |
| 12000 | 0 | -24576 |
| 15999 | 8192 | -8192 |

The expected amplitudes and half-open interval boundaries are independent test
oracles. FFmpeg's WAV demuxer independently reads sample rate, channel count,
duration and decoded PCM. Browser audio decode verifies exact source-frame
samples. Silence does not imply a transcript or automatic review.
