# Nginx on the receiver

Nginx is the receiver's web server. It is a normal program waiting for web
requests on TCP port 80.

When sender runs this:

```bash
curl -I http://192.168.150.20
```

it asks receiver for the web page. Nginx answers with an HTTP response, often
`HTTP/1.1 200 OK`.

## What it serves now

Right now Nginx serves its default Debian welcome page. The default page file
is normally:

```text
/var/www/html/index.nginx-debian.html
```

You do not need to change the page yet. Its job is simply to give us a known,
healthy service to check before and after later experiments.

## Commands you need now

Run these on `syn-receiver`:

```bash
systemctl is-active nginx
sudo systemctl status nginx
sudo systemctl restart nginx
```

`active` means the web server is running. `restart` stops and starts it again
if you later change its configuration or page.

To see whether it is listening on web port 80:

```bash
sudo ss -ltnp | grep ':80'
```

The useful idea is simple: `0.0.0.0:80` means Nginx accepts IPv4 web requests
on port 80 from its connected networks, including our private lab network.

## What Nginx does not do

Nginx does not create the SYN handshake. The sender's operating system does
that for ordinary `curl` traffic. Nginx receives a connection only after the
TCP handshake finishes. This makes Nginx useful as the normal service we test
with `curl`.

