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

    // Extract Subdomain(s)
    let subdomains = [];
    const hostname = window.location.hostname;
    const pathname = window.location.pathname;

    if (hostname.includes(".club.hotmart.com")) {
        subdomains.push(hostname.split(".")[0]);
    } else {
        const clubMatch = pathname.match(/\/club\/([^/]+)/);
        if (clubMatch) {
            subdomains.push(clubMatch[1]);
        }
    }

    // Scan localStorage / sessionStorage for all subdomains
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        const val = localStorage.getItem(key);
        if (key && key.includes("club") && val && typeof val === "string" && val.length < 50) {
            if (!subdomains.includes(val) && !val.includes("{")) subdomains.push(val);
        }
    }

    // Extract Product ID(s)
    let productIds = [];
    const prodMatch = pathname.match(/\/(?:products|player)\/([0-9]+)/);
    if (prodMatch) {
        productIds.push(prodMatch[1]);
    }

    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key.includes("productId") || key.includes("product-id"))) {
            const val = localStorage.getItem(key);
            if (val && !productIds.includes(val)) productIds.push(val);
        }
    }

    const payload = {
        token: tokenFound,
        subdomain: subdomains.length === 1 ? subdomains[0] : subdomains,
        product_id: productIds.length === 1 ? productIds[0] : productIds
    };

    const outputJSON = JSON.stringify(payload, null, 2);
    copy(outputJSON);
    alert("Token & Course Info JSON copied to clipboard!\n\nYou can paste this JSON (or just the token) into the 'Bearer / SSO Token' box in the Web app.");
})();

