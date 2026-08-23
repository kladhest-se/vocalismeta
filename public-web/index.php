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
    ['Finds the right recording', 'Matches your files against regional Audible catalogues, and Ljudboksarkivet for Swedish audiobooks.'],
    ['Fills in the shelf', 'Authors, narrators, series, sequence, summaries, and covers, kept complete across multi-part books.'],
    ['Stable identities', 'Players read the same book, work, and contributor identities every time they talk to Plex.'],
    ['Nothing else to run', 'The agent lives inside Plex. No companion service, no database, no extra port to open.'],
];

$platforms = ['macOS', 'iPhone', 'iPad', 'Apple TV'];

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
  <meta name="description" content="A Plex audiobook metadata agent that gives your audiobooks the right titles, narrators, series, and covers.">
  <meta name="theme-color" content="#1e1e2e">
  <title><?= e($project['name']) ?> — Plex audiobook metadata agent</title>
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="bar">
  <a class="brand" href="#top" aria-label="<?= e($project['name']) ?> home">
    <span class="mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
    <span><?= e($project['name']) ?></span>
  </a>
  <nav aria-label="Primary">
    <a href="#install">Install</a>
    <a href="<?= e($project['github_web']) ?>">GitHub</a>
  </nav>
</header>

<main id="top">
  <section class="hero">
    <span class="tile" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>
    <p class="eyebrow">Plex audiobook metadata agent</p>
    <h1>Your audiobooks,<br>properly labelled.</h1>
    <p class="lead">VocalisMeta reads your audiobook files, finds the real recording behind them, and writes the details straight into Plex.</p>
    <div class="actions">
      <a class="button primary" href="#install">Install on Plex</a>
      <a class="button quiet" href="<?= e($project['github_web']) ?>">View source</a>
    </div>
    <p class="meta">Version <?= e($project['version']) ?> · Free and open source</p>
  </section>

  <section class="cards" aria-label="What VocalisMeta does">
    <?php foreach ($features as [$title, $description]): ?>
      <article class="card">
        <h2><?= e($title) ?></h2>
        <p><?= e($description) ?></p>
      </article>
    <?php endforeach; ?>
  </section>

  <section class="install" id="install">
    <h2>Two commands, then pick the agent.</h2>
    <p>The installer validates the bundle, restarts Plex, checks the startup log, and rolls back on its own if anything fails.</p>
    <div class="code">
      <span class="code-label">Stable release</span>
      <pre><code>curl -fsSL <?= e($project['installer']) ?> |
  sudo bash -s -- --release v<?= e($project['version']) ?></code></pre>
      <span class="code-label">Latest development build</span>
      <pre><code>curl -fsSL <?= e($project['installer']) ?> |
  sudo bash -s -- --developer</code></pre>
    </div>
    <p class="after">In your Plex music library, open <strong>Advanced</strong>, choose <strong>VocalisMeta Agent</strong>, then refresh metadata.</p>
    <p class="identity">Building a player? Books arrive with identities such as <code>spokenmeta:audible:us:B08G9PRS1K</code>. <a href="<?= e($project['github_web']) ?>/blob/main/client-contract/metadata-contract-v3.json">Read contract v3</a></p>
  </section>

  <section class="player">
    <h2>Made to be heard in VocalisBook.</h2>
    <p>An audiobook-first player for your Plex library.</p>
    <p class="platforms"><?php foreach ($platforms as $platform): ?><span><?= e($platform) ?></span><?php endforeach; ?></p>
    <a class="button quiet" href="<?= e($project['player_web']) ?>">Discover VocalisBook</a>
  </section>
</main>

<footer>
  <div class="footer-support" aria-label="Support VocalisMeta on Ko-fi">
    <script type="text/javascript" src="https://storage.ko-fi.com/cdn/widget/Widget_2.js"></script>
    <script type="text/javascript">kofiwidget2.init('Support me on Ko-fi', '#73a9f5', 'R7P325M7NE');kofiwidget2.draw();</script>
  </div>
  <div class="footer-links">
    <a href="<?= e($project['github_web']) ?>">GitHub</a>
    <a href="<?= e($project['github_web']) ?>/blob/main/README.md">Documentation</a>
    <a href="<?= e($project['player_web']) ?>">VocalisBook</a>
    <a href="<?= e($project['github_web']) ?>/blob/main/LICENSE">MIT License</a>
  </div>
  <p class="footer-note">Metadata for audiobooks in Plex.</p>
</footer>
</body>
</html>
