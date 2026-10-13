"""Authored mathematical PCM only; no acquired audio or accuracy claim (CC0)."""
import io
import math
import struct
import wave


def wav(index):
    """Selected channel contains low/high tone; other channel and margins oppose it."""
    selected = index % 2
    frequency = 500 if index % 2 == 0 else 2000
    samples = []
    for frame in range(2048):
        channels = []
        for channel in range(2):
            freq = frequency if channel == selected and 256 <= frame < 1280 else 3000 - frequency
            channels.append(round((9000 + index * 31) * math.sin(2 * math.pi * freq * frame / 8000 + index * .017)))
        samples.append(struct.pack('<hh', *channels))
    target = io.BytesIO()
    with wave.open(target, 'wb') as writer:
        writer.setparams((2, 2, 8000, 0, 'NONE', 'not compressed'))
        writer.writeframes(b''.join(samples))
    return target.getvalue()


def segment(index):
    return dict(start_frame=256, end_frame=1280, channel=index % 2, transcript='',
                label='low tone' if index % 2 == 0 else 'high tone', speaker='')
