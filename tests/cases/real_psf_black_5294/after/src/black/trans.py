        * The line is a dictionary key assignment where some valid key is being
          assigned the value of some string.
          OR
        * The line is a lambda expression and the value is a string.
          OR
        * The line starts with an "atom" string that prefers to be wrapped in
          parens. It's preferred to be wrapped when it's is an immediate child of
            if (current_state, next_token) in self._goto:
                self._state = self._goto[current_state, next_token]
            else:
                # Otherwise, we check if the current state was assigned a
                # default.
                if (current_state, self.DEFAULT_TOKEN) in self._goto:
                    self._state = self._goto[current_state, self.DEFAULT_TOKEN]
