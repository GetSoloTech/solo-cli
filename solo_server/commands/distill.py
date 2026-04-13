import typer
import subprocess
import os
from huggingface_hub import HfApi

app = typer.Typer()

def run_command(command):
    """
    Runs a shell command and prints output.
    """
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        typer.echo(result.stdout)
    except subprocess.CalledProcessError as e:
        typer.echo(f"❌ Command failed: {e.stderr}", err=True)


@app.command()
def distill(
    teacher_model: str,
    student_model: str,
    dataset_name: str,
    output_dir: str = "./distilled_model",
    num_train_epochs: int = 3,
    per_device_train_batch_size: int = 1,
    gradient_accumulation_steps: int = 8,
    learning_rate: float = 2e-5,
    alpha: float = 0.5,
    temperature: float = 2.0,
    use_flash_attention: bool = True,
    bf16: bool = True,
):
    """
    Runs model distillation using DistillKit.
    """
    typer.echo(f"🚀 Starting distillation with teacher: {teacher_model}, student: {student_model}")

    command = [
        "python", "distill.py",
        "--teacher-model", teacher_model,
        "--student-model", student_model,
        "--dataset-name", dataset_name,
        "--output-dir", output_dir,
        "--num-train-epochs", str(num_train_epochs),
        "--per-device-train-batch-size", str(per_device_train_batch_size),
        "--gradient-accumulation-steps", str(gradient_accumulation_steps),
        "--learning-rate", str(learning_rate),
        "--alpha", str(alpha),
        "--temperature", str(temperature),
        "--use-flash-attention", str(use_flash_attention),
        "--bf16", str(bf16)
    ]

    run_command(command)
    typer.echo(f"✅ Distillation complete! Model saved at {output_dir}")

    api = HfApi()
    api.upload_file(
        path_or_fileobj=output_dir,
        path_in_repo="distilled_model",
        repo_id="solo-ai/distilled-model",
        repo_type="space",
    )
    typer.echo(f"✅ Model uploaded to Hugging Face!")   

if __name__ == "__main__":
    app()