"""Matinee: a film picker for a home media library."""

# Sent with every request Matinee makes. A default library agent string is refused by some proxies in front of a
# household's services (a Cloudflare bot rule answers Python-urllib with 403).
USER_AGENT = "Matinee/0.1"
