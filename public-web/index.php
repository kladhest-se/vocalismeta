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
  <meta name="theme-color" content="#1e1e2e">
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
    <p class="eyebrow">Plex audiobook metadata agent</p>
    <h1>Clean metadata for<br><em>better listening.</em></h1>
    <p class="lead">VocalisMeta organizes audiobook libraries with accurate recording data, authors, narrators, series, covers, and stable identities—all stored directly in Plex.</p>
    <div class="hero-actions">
      <a class="button primary" href="#install">Install VocalisMeta <span>→</span></a>
      <a class="button secondary" href="<?= e($project['github_web']) ?>/blob/main/CLIENT_INTEGRATION.md">Player integration</a>
    </div>
    <div class="hero-meta"><span>v<?= e($project['version']) ?></span><span>Runs inside Plex</span><span>No separate service</span></div>
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
      <h2>The details a music library leaves out.</h2>
      <p>Recording metadata remains authoritative, enrichment fills only the gaps, and local choices stay under your control.</p>
    </div>
    <div class="feature-list">
      <?php foreach ($features as $index => [$title, $description]): ?>
        <article class="feature">
          <span class="feature-number">0<?= $index + 1 ?></span>
          <h3><?= e($title) ?></h3>
          <p><?= e($description) ?></p>
        </article>
      <?php endforeach; ?>
    </div>
  </section>

  <section class="section architecture" id="architecture">
    <div class="section-heading">
      <p class="section-label">Inside Plex, where it belongs</p>
      <h2>One path. No companion server.</h2>
      <p>VocalisMeta talks to metadata providers during matching and writes the result into Plex. Audiobook players continue talking only to Plex.</p>
    </div>
    <div>
      <ol class="flow">
        <?php foreach ($flow as $index => $step): ?>
          <li><span>0<?= $index + 1 ?></span><strong><?= e($step) ?></strong></li>
        <?php endforeach; ?>
      </ol>
      <div class="contract">
        <strong>Stable identity contract</strong>
        <code>spokenmeta:audible:us:B08G9PRS1K</code>
        <p>Clients can use stable recording, work, and contributor identities directly from Plex.</p>
        <a class="text-link" href="<?= e($project['github_web']) ?>/blob/main/client-contract/metadata-contract-v3.json">Machine-readable contract v3 →</a>
      </div>
    </div>
  </section>

  <section class="section player-promo" id="player">
    <div class="player-copy">
      <p class="section-label">Recommended audiobook player</p>
      <h2>Metadata made to be heard.</h2>
      <p>Pair VocalisMeta with VocalisBook for an audiobook-first Plex experience across your Apple devices.</p>
      <div class="platforms"><span>macOS</span><span>iPhone</span><span>iPad</span><span>Apple TV</span></div>
      <a class="button primary" href="<?= e($project['player_web']) ?>">Discover VocalisBook <span>→</span></a>
    </div>
    <span class="player-mark" aria-hidden="true">V</span>
  </section>

  <section class="section install" id="install">
    <div class="install-copy">
      <p class="section-label">Direct installation</p>
      <h2>Install directly on Plex.</h2>
      <p>The installer validates the bundle, restarts Plex, checks startup, and rolls back automatically if validation fails.</p>
      <ul><li>Static development version <?= e($project['version']) ?></li><li>Runs entirely inside Plex</li><li>No companion service</li></ul>
      <a class="repository-link" href="<?= e($project['github_web']) ?>">View source and documentation on GitHub →</a>
    </div>
    <div class="terminal">
      <div class="terminal-top">INSTALL</div>
      <pre><code><span>$</span> curl -fsSL \
  <?= e($project['installer']) ?> | \
  sudo bash -s -- --release v<?= e($project['version']) ?>

<span>$</span> curl -fsSL \
  <?= e($project['installer']) ?> | \
  sudo bash -s -- --developer</code></pre>
    </div>
  </section>

  <footer>
    <a class="brand" href="#top"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><span>VocalisMeta</span></a>
    <p>Metadata for audiobooks in Plex.</p>
    <div class="footer-support" aria-label="Support VocalisMeta on Ko-fi">
      <script type="text/javascript" src="https://storage.ko-fi.com/cdn/widget/Widget_2.js"></script>
      <script type="text/javascript">kofiwidget2.init('Support me on Ko-fi', '#73a9f5', 'R7P325M7NE');kofiwidget2.draw();</script>
    </div>
    <div class="footer-links"><a href="<?= e($project['github_web']) ?>">GitHub</a><a href="<?= e($project['player_web']) ?>">VocalisBook</a><a href="<?= e($project['github_web']) ?>/blob/main/README.md">Documentation</a><a href="<?= e($project['github_web']) ?>/blob/main/LICENSE">MIT License</a></div>
  </footer>
</main>
</body>
</html>
