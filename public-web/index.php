<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: strict-origin-when-cross-origin');
    header("Permissions-Policy: camera=(), microphone=(), geolocation=()");
}

$project = [
    'name' => 'VocalisMeta',
    'version' => '0.1.0',
    'github_web' => 'https://github.com/kladhest-se/vocalismeta',
    'installer' => 'https://raw.githubusercontent.com/kladhest-se/vocalismeta/main/scripts/install-on-plex.sh',
    'player_web' => 'https://vocalisbook.kladhest.se',
];

$features = [
    ['Regional matching', 'Searches multiple Audible marketplaces and scores the correct audiobook edition, narrator, runtime, and format.'],
    ['Swedish catalogue', 'Optionally matches Swedish audiobooks through Ljudboksarkivet and stores the result directly in Plex.'],
    ['Thoughtful enrichment', 'Uses Open Library and Google Books only to fill gaps without replacing stronger recording metadata.'],
    ['Artwork that holds up', 'Reads local and embedded covers, validates remote images, retries downloads, and removes stale posters.'],
    ['Built for real libraries', 'Understands multi-part books, embedded ASIN, region, ISBN, LibriVox IDs, series, and sequence tags.'],
];

$sources = ['Audible', 'Ljudboksarkivet', 'Open Library', 'Google Books', 'LibriVox', 'Embedded tags'];
$flow = ['Audio files', 'VocalisMeta', 'Plex library', 'Audiobook player'];

function e(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="A lightweight metadata agent that makes audiobook libraries feel native in Plex.">
  <meta name="theme-color" content="#0a0c0c">
  <title><?= e($project['name']) ?> — Plex audiobook metadata</title>
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
<main>
  <header class="site-header">
    <a class="brand" href="#top" aria-label="VocalisMeta home">
      <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
      <span><?= e($project['name']) ?></span>
    </a>
    <nav aria-label="Primary navigation">
      <a href="#features">Features</a>
      <a href="#architecture">How it works</a>
      <a href="<?= e($project['player_web']) ?>">VocalisBook</a>
      <a href="#install">Install</a>
      <a class="nav-cta" href="<?= e($project['github_web']) ?>">GitHub</a>
    </nav>
  </header>

  <section class="hero" id="top">
    <div class="hero-copy">
      <div class="eyebrow"><span></span> Plex audiobook metadata agent</div>
      <h1>Better metadata.<br><em>Better listening.</em></h1>
      <p class="lead">VocalisMeta turns audiobook files into a clean, richly organized Plex library—using trusted catalog data, embedded tags, and your local artwork.</p>
      <div class="hero-actions">
        <a class="button primary" href="#install">Install VocalisMeta <span>→</span></a>
        <a class="button secondary" href="<?= e($project['github_web']) ?>/blob/main/CLIENT_INTEGRATION.md">Player integration</a>
      </div>
      <div class="hero-meta"><span>v<?= e($project['version']) ?></span><span>Runs inside Plex</span><span>No separate service</span></div>
    </div>

    <div class="hero-visual" aria-label="Example audiobook metadata card">
      <div class="glow"></div>
      <div class="book-cover">
        <span class="cover-kicker">AUDIOBOOK</span>
        <strong>THE<br>LONG<br>STORY</strong>
        <span class="cover-author">A. N. AUTHOR</span>
        <div class="sound-lines"><i></i><i></i><i></i><i></i><i></i></div>
      </div>
      <div class="metadata-card">
        <div class="status"><span></span> MATCHED · AUDIBLE US</div>
        <h2>The Long Story</h2>
        <p>A. N. Author · Narrated by N. Reader</p>
        <div class="tags"><span>Series: Great Tales</span><span>Book 3</span></div>
        <div class="meter"><i></i></div>
        <div class="card-foot"><span>11h 42m</span><span>Unabridged</span><span>English</span></div>
      </div>
    </div>
  </section>

  <section class="sources" aria-label="Metadata sources">
    <span>METADATA FROM</span>
    <?php foreach ($sources as $index => $source): ?>
      <strong><?= e($source) ?></strong><?php if ($index < count($sources) - 1): ?><i></i><?php endif; ?>
    <?php endforeach; ?>
  </section>

  <section class="section" id="features">
    <div class="section-heading">
      <p class="section-label">Designed for audiobooks</p>
      <h2>Your files already tell a story.<br>VocalisMeta fills in the details.</h2>
      <p>Provider metadata stays authoritative, enrichment fills only missing fields, and local choices remain under your control.</p>
    </div>
    <div class="feature-grid">
      <?php foreach ($features as $index => [$title, $description]): ?>
        <article class="feature">
          <span class="feature-number">0<?= $index + 1 ?></span>
          <div class="feature-icon icon-<?= $index + 1 ?>" aria-hidden="true"><i></i><b></b></div>
          <h3><?= e($title) ?></h3>
          <p><?= e($description) ?></p>
        </article>
      <?php endforeach; ?>
    </div>
  </section>

  <section class="section architecture" id="architecture">
    <div class="section-heading compact">
      <p class="section-label">Inside Plex, where it belongs</p>
      <h2>One metadata path.<br>No extra service to run.</h2>
    </div>
    <div class="flow">
      <?php foreach ($flow as $index => $step): ?>
        <div class="flow-step">
          <span><?= $index + 1 ?></span><strong><?= e($step) ?></strong>
          <?php if ($index < count($flow) - 1): ?><i aria-hidden="true">→</i><?php endif; ?>
        </div>
      <?php endforeach; ?>
    </div>
    <div class="contract">
      <div><span class="contract-dot"></span><p>Stable identity contract</p></div>
      <code>spokenmeta:audible:us:B08G9PRS1K</code>
      <p>Clients can use stable recording and work keys plus optional Contract v3 contributor, publication, production, and rating metadata—all through Plex.</p>
      <a href="<?= e($project['github_web']) ?>/blob/main/client-contract/metadata-contract-v3.json">Machine-readable contract v3 →</a>
    </div>
  </section>

  <section class="section player-promo" id="player">
    <div class="player-copy">
      <p class="section-label">Recommended audiobook player</p>
      <h2>Metadata made to be heard.</h2>
      <p>Pair VocalisMeta with VocalisBook for an audiobook-first Plex experience across your Apple devices.</p>
      <a class="button primary" href="<?= e($project['player_web']) ?>">Discover VocalisBook <span>→</span></a>
    </div>
    <div class="player-card">
      <span class="player-mark">V</span>
      <div><strong>VocalisBook</strong><p>Audiobooks from your Plex library.</p></div>
      <div class="player-platforms"><span>macOS</span><span>iPhone</span><span>iPad</span><span>Apple TV</span></div>
    </div>
  </section>

  <section class="section install" id="install">
    <div class="install-copy">
      <p class="section-label">Direct installation</p>
      <h2>A clean, predictable Plex bundle.</h2>
      <p>Run the public installer for the stable release or the latest developer build. It validates the bundle, restarts Plex, checks startup, and rolls back on failure.</p>
      <ul><li>Static development version <?= e($project['version']) ?></li><li>Runs entirely inside Plex</li><li>No companion service</li></ul>
    </div>
    <div class="terminal">
      <div class="terminal-top"><span></span><span></span><span></span><b>INSTALL</b></div>
      <pre><code><span>$</span> curl -fsSL \
  <?= e($project['installer']) ?> | \
  sudo bash -s -- --release v<?= e($project['version']) ?>

<span>$</span> curl -fsSL \
  <?= e($project['installer']) ?> | \
  sudo bash -s -- --developer</code></pre>
    </div>
    <div class="repository-card">
      <p class="section-label">Public source repository</p>
      <strong>GitHub</strong>
      <code><?= e($project['github_web']) ?></code>
    </div>
  </section>

  <footer>
    <a class="brand" href="#top"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><span>VocalisMeta</span></a>
    <p>Metadata for audiobooks in Plex.</p>
    <div><a href="<?= e($project['github_web']) ?>">GitHub</a><a href="<?= e($project['player_web']) ?>">VocalisBook</a><a href="<?= e($project['github_web']) ?>/blob/main/README.md">Documentation</a><a href="<?= e($project['github_web']) ?>/blob/main/LICENSE">MIT License</a></div>
  </footer>
</main>
</body>
</html>
