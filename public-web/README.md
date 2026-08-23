# VocalisMeta public website

This is the lightweight public landing page for VocalisMeta. It uses plain PHP
and CSS, has no package-manager dependencies, and does not need a database. The
only third-party asset is the Ko-fi support widget loaded from Ko-fi's CDN.

## Run locally

```bash
php -S 127.0.0.1:8080 -t public-web
```

Then open `http://127.0.0.1:8080/`.

## Deploy

Point the document root of any PHP 7.4+ virtual host at `public-web`. The page
is also valid on PHP 8.x. Update the `$project` array at the top of `index.php`
if either repository address or the displayed version changes.
