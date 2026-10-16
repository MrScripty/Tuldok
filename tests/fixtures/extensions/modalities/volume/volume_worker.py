from pathlib import Path
Path(__file__).with_name("EXECUTED").write_text("Package source imported")
raise RuntimeError("Inert modality fixture must never execute")

def read():
    raise RuntimeError("No modality reader is implemented")
