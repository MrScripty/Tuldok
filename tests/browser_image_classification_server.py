"""Local seeded service for the classifier export browser gate."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'fixtures'))
from app import Dataset, main
from image_classification_fixture import populate

if __name__ == '__main__':
    folder = sys.argv[sys.argv.index('--data') + 1]
    dataset = Dataset(folder)
    try:
        populate(dataset)
    finally:
        dataset.close()
    main()
