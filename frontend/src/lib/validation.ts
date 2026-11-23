const allowedHosts = new Set([
  'youtube.com',
  'www.youtube.com',
  'm.youtube.com',
  'youtu.be',
  'facebook.com',
  'www.facebook.com',
  'm.facebook.com',
  'fb.watch',
])

export function validateVideoUrl(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return 'Paste a video link to continue.'
  if (trimmed.length > 2048) return 'That link is too long. Use the address bar copy option.'

  let parsed: URL
  try {
    parsed = new URL(trimmed)
  } catch {
    return 'That link doesn’t look right. Paste the full https:// address.'
  }

  if (parsed.protocol !== 'https:') {
    return 'Use an https:// link from YouTube or Facebook.'
  }
  if (parsed.username || parsed.password || parsed.port) {
    return 'Use a plain video link without a port or sign-in details.'
  }
  if (!allowedHosts.has(parsed.hostname.toLowerCase())) {
    return 'VidMax currently recognizes YouTube and Facebook links.'
  }
  if (parsed.pathname === '/' && parsed.hostname !== 'youtu.be' && parsed.hostname !== 'fb.watch') {
    return 'Paste the address of a specific video, not the site homepage.'
  }

  return null
}
