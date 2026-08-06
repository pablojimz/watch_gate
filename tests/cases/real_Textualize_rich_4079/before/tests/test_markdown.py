    assert result == expected


if __name__ == "__main__":
    markdown = Markdown(MARKDOWN)
    rendered = render(markdown)
