
        # Return a plain path if neither host or subdomain matching is enabled,
        # or if they are enabled and the current host matches.
        if (
            not force_external
            and (self.map.subdomain_matching or self.map.host_matching)
            and (
                (self.map.subdomain_matching and domain_part == self.subdomain)
                or (self.map.host_matching and host == self.server_name)
            )
        ):
            return f"{self.script_name.rstrip('/')}/{path.lstrip('/')}"

