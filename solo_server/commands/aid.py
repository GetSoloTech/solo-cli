import sys
import typer
from litgpt import LLM
from rich.console import Console

console = Console()

def query_llm(query: str):
    # Check if the query exceeds 9000 characters
    if len(query) > 9000:
        typer.echo("Error: Your query exceeds the maximum allowed length of 9000 characters. It's over 9000!")
        raise typer.Exit(1)
    
    # Load the model and generate a response while showing a spinner
    llm = LLM.load("Qwen/Qwen2.5-1.5B-Instruct")
    with console.status("Generating response...", spinner="dots"):
        response = llm.generate(query)
    typer.echo(response)

def interactive_mode():
    console.print("Interactive Mode (type 'exit' or 'quit' to end):", style="bold green")
    while True:
        query_text = input(">> ")
        if query_text.lower() in ("exit", "quit"):
            break
        query_llm(query_text)

if __name__ == "__main__":
    # If invoked with "@@" as the first argument, treat the rest as the query.
    # Otherwise, launch interactive mode.
    if len(sys.argv) > 1 and sys.argv[1] == "@@":
        if len(sys.argv) > 2:
            query_text = " ".join(sys.argv[2:])
        else:
            typer.echo("Enter your query (end with EOF / Ctrl-D):")
            query_text = sys.stdin.read().strip()
        query_llm(query_text)
    else:
        interactive_mode()
