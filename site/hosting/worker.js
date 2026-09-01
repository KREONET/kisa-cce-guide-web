/** Serve the generated static guide through the Sites asset binding. */

const hasFileExtension = (pathname) => /\/[^/]+\.[^/]+$/.test(pathname);

const fetchAsset = (request, env, pathname) => {
  const assetUrl = new URL(request.url);
  assetUrl.pathname = pathname;
  return env.ASSETS.fetch(new Request(assetUrl, request));
};

const worker = {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", {
        status: 405,
        headers: {Allow: "GET, HEAD"},
      });
    }

    const directResponse = await env.ASSETS.fetch(request);
    if (directResponse.status !== 404) {
      return directResponse;
    }

    const url = new URL(request.url);
    const routePath = url.pathname.endsWith("/")
      ? `${url.pathname}index.html`
      : hasFileExtension(url.pathname)
        ? null
        : `${url.pathname}/index.html`;
    if (routePath !== null) {
      const routeResponse = await fetchAsset(request, env, routePath);
      if (routeResponse.status !== 404) {
        return routeResponse;
      }
    }

    const notFoundResponse = await fetchAsset(request, env, "/404.html");
    return new Response(notFoundResponse.body, {
      status: 404,
      headers: notFoundResponse.headers,
    });
  },
};

export default worker;
