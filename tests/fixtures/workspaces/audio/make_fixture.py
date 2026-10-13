"""Reproduce the authored two-second stereo impulse WAV (no acquired audio)."""
from pathlib import Path
import struct
import wave

SAMPLE_RATE = 8000
FRAMES = 16000
IMPULSES = {(0, 0): 16384, (8000, 0): -16384, (15999, 0): 8192,
            (4000, 1): 24576, (12000, 1): -24576, (15999, 1): -8192}

if __name__ == '__main__':
    destination = Path(__file__).with_name('stereo-impulses.wav')
    with wave.open(str(destination), 'wb') as writer:
        writer.setnchannels(2); writer.setsampwidth(2); writer.setframerate(SAMPLE_RATE)
        writer.writeframes(b''.join(struct.pack('<hh', *(IMPULSES.get((frame, channel), 0) for channel in range(2)))
                                  for frame in range(FRAMES)))
    print(destination)
