# Aviso: Malicious code in spf-analytics (npm) (GHSA-688c-c373-7xcv)

## Resumen

index.js is a heavily obfuscated browser script (obfuscator.io-style string-array + rotation) advertised for inclusion via unpkg on Shopify-style storefronts. At runtime it listens for the 'gokwik_events' window event and harvests customer name, phone, email, full address, city, state, country, pincode, cart line items, order total, and payment method. The captured PII is encrypted with a hardcoded RSA-OAEP public key wrapping an AES-GCM session key and POSTed to https://connector.internalwebhooks.com/spf-analytics, a destination the storefront operator did not configure. A localStorage key ('shopify_analytics_cache_7f4c91d8b2e64a0f9c37d5ab81e26f43') holds up to 500 fingerprints to suppress duplicate uploads, and a __spfAddressForwarderLoaded flag guards against double-loading. The endpoint URL, PEM key, event name, and field names are all indirected through the obfuscator string table, concealing the destination and captured fields from casual inspection of the CDN-served bundle. The package presents itself as 'analytics' but the relay is to a non-first-party endpoint hardcoded by the author, encrypted to prevent network inspection, and never disclosed to the operator embedding the script.

## Paquetes afectados

- `spf-analytics` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-688c-c373-7xcv

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `spf-analytics`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
