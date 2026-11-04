"""URL Validation and SSRF Protection for Job Discovery.
Ensures only valid, safe, public HTTP/HTTPS URLs are processed and fetched.
"""
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

logger = logging.getLogger(__name__)

# Tracking query parameters to strip for canonicalization
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'ref', 'fbclid', 'gclid', 'msclkid', 'trk', 'trackingId', 'midToken',
    'origin', 'source', 'from', 'context', 'sessionId', 'sc_src'
}

def is_safe_ip(ip_str: str) -> bool:
    """Check if an IP address is a public, non-private, non-loopback, non-reserved address."""
    try:
        ip = ipaddress.ip_address(ip_str)
        # Block private, loopback, link-local, reserved, multicast, unspecified
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
        # Block IPv4-mapped IPv6 addresses representing private IPv4
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return is_safe_ip(str(ip.ipv4_mapped))
        # Block cloud metadata service IP (169.254.169.254)
        if str(ip) == '169.254.169.254':
            return False
        return True
    except ValueError:
        return False

def validate_url(url: str, allow_private: bool = False) -> tuple[bool, str]:
    """Validate that a URL is safe to fetch and has valid syntax.
    Returns (is_valid, error_reason).
    """
    if not url or not isinstance(url, str):
        return False, "URL is empty or not a string"

    url = url.strip()
    if len(url) > 2048:
        return False, "URL exceeds maximum length"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL syntax: {e}"

    if parsed.scheme.lower() not in ('http', 'https'):
        return False, f"Unsupported URL scheme: {parsed.scheme}"

    hostname = (parsed.hostname or '').strip().lower()
    if not hostname:
        return False, "URL has no valid hostname"

    # Block localhost and common local domain names
    if hostname in ('localhost', '127.0.0.1', '::1', '0.0.0.0', 'metadata.google.internal'):
        return False, "Localhost or metadata domain is rejected"

    if hostname.endswith('.local') or hostname.endswith('.internal') or hostname.endswith('.localhost'):
        return False, "Internal network domain is rejected"

    # Check port
    if parsed.port and parsed.port not in (80, 443, 8080):
        return False, f"Non-standard port rejected: {parsed.port}"

    if not allow_private:
        # Resolve hostname to verify IP safety
        try:
            # Check if hostname itself is an IP literal
            try:
                ipaddress.ip_address(hostname)
                if not is_safe_ip(hostname):
                    return False, f"Private or reserved IP address rejected: {hostname}"
            except ValueError:
                # Hostname is a domain name, resolve via DNS
                addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
                for item in addr_info:
                    ip = item[4][0]
                    if not is_safe_ip(ip):
                        return False, f"Hostname resolves to private/reserved IP: {ip}"
        except socket.gaierror as e:
            # Temporary DNS error or non-existent domain
            logger.debug(f"DNS resolution failed for {hostname}: {e}")
            return False, f"Cannot resolve hostname: {hostname}"
        except Exception as e:
            return False, f"Safety check failed: {e}"

    return True, ""

def canonicalize_url(url: str) -> str:
    """Normalize a job URL by removing tracking parameters, fragments, and standardizing casing."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        
        # Remove standard default ports from netloc
        if netloc.endswith(':80') and scheme == 'http':
            netloc = netloc[:-3]
        elif netloc.endswith(':443') and scheme == 'https':
            netloc = netloc[:-4]

        # Strip trailing slashes on root path
        path = parsed.path.rstrip('/') or '/'

        # Filter out tracking params
        query_items = parse_qsl(parsed.query, keep_blank_values=False)
        cleaned_query = [
            (k, v) for k, v in query_items
            if k.lower() not in TRACKING_PARAMS and not k.lower().startswith('utm_')
        ]
        # Sort query params for deterministic canonical URL
        cleaned_query.sort(key=lambda x: x[0])
        new_query = urlencode(cleaned_query)

        # No fragment
        return urlunparse((scheme, netloc, path, parsed.params, new_query, ''))
    except Exception:
        return url.split('#')[0].rstrip('/')
