        self.justify = justify

    def on_text(self, context: MarkdownContext, text: TextType) -> None:
        if isinstance(text, str):
            self.content.append(text, context.current_style)
        else:
            self.content.append_text(text)


class ListElement(MarkdownElement):
