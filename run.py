"""Project entry point for the new modular pipeline."""

from pipeline.runner import run_pipeline


if __name__ == "__main__":
    run_pipeline(seller="seller_001", mode="daily")

