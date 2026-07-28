(function () {
    let tokenFound = null;
    for (let i = 0; i < localStorage.length; i++) {
        const value = localStorage.getItem(localStorage.key(i));
        if (value && value.includes("eyJ")) {
            const match = value.match(/eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*/);
            if (match) { tokenFound = match[0]; break; }
        }
    }
    if (!tokenFound) {
        for (let i = 0; i < sessionStorage.length; i++) {
            const value = sessionStorage.getItem(sessionStorage.key(i));
            if (value && value.includes("eyJ")) {
                const match = value.match(/eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*/);
                if (match) { tokenFound = match[0]; break; }
            }
        }
    }

    if (!tokenFound) {
        alert("Token not found. Make sure you are logged into your Hotmart course player page.");
        return;
    }

    // Extract Subdomain
    let subdomain = "";
    const hostname = window.location.hostname;
    const pathname = window.location.pathname;

    if (hostname.includes(".club.hotmart.com")) {
        subdomain = hostname.split(".")[0];
    } else {
        const clubMatch = pathname.match(/\/club\/([^/]+)/);
        if (clubMatch) {
            subdomain = clubMatch[1];
        }
    }

    // Extract Product ID
    let productId = "";
    const prodMatch = pathname.match(/\/(?:products|player)\/([0-9]+)/);
    if (prodMatch) {
        productId = prodMatch[1];
    } else {
        // Fallback search in localStorage
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && (key.includes("productId") || key.includes("product-id"))) {
                productId = localStorage.getItem(key);
                break;
            }
        }
    }

    const output = `TOKEN="${tokenFound}"\nSUBDOMAIN="${subdomain}"\nPRODUCT_ID="${productId}"`;
    copy(output);
    alert("Token configuration successfully copied to clipboard!\\n\\nPaste it directly inside the 'Bearer Token or SSO Token' box in the Web app.");
})();
