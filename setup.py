from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="solo-cli",
    version="0.6.1",
    author="Dhruv Diddi",
    author_email="dhruv.diddi@gmail.com",
    description="CLI for Physical AI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/GetSoloTech/solo-cli",
    packages=find_packages(include=["solo", "solo.*"]),
    include_package_data=True,
    package_data={
        "solo.config": ["*.yaml"],
        "solo.udev": ["*.rules"],
    },
    install_requires=[
        "typer",
        "GPUtil",
        "psutil",
        "requests", 
        "rich",
        "huggingface_hub",
        "pydantic",
        "lerobot[feetech,dynamixel] @ git+https://github.com/GetSoloTech/solo-bot.git@main",
        "transformers",
        "accelerate",
        "num2words"
    ],
    extras_require={
        "dev": ["pytest", "black", "isort"],
    },
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "solo=solo.cli:app",
        ],
    },
)