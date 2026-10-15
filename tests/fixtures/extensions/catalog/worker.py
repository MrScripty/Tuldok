from pathlib import Path
Path(__file__).with_name("EXECUTED").write_text("discovery must not execute")
raise RuntimeError("never import or launch")
