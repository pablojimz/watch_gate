import click


@click.command()
@click.option('--name', default='mundo')
def main(name):
    click.echo(f'hola {name}')
