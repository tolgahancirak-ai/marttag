const adminCopy = {
  ar: {
    announcement: "إدارة طلبات Epgyt Market — الدخول لأصحاب المتجر فقط",
    languageLabel: "اختيار اللغة", shopLink: "العودة للمتجر",
    dashboardKicker: "إدارة المتجر", dashboardTitle: "الطلبات",
    refresh: "تحديث الطلبات", logout: "تسجيل الخروج", adminToken: "رمز دخول الإدارة",
    signIn: "دخول آمن", tokenHelp: "رمز الدخول موجود في إعداد NILEMARKET_ADMIN_TOKEN على الخادم.",
    privacyNote: "بيانات العملاء خاصة. لا تشارك رابط لوحة الإدارة أو رمز الدخول.",
    adminFooter: "لوحة خاصة بإدارة المتجر.", loading: "جارٍ تحميل الطلبات…",
    loginRequired: "أدخل رمز الإدارة للمتابعة.", loadError: "تعذّر تحميل الطلبات. تحقق من الرمز واتصال الخادم.",
    updateError: "تعذّر تحديث حالة الطلب.", empty: "لا توجد طلبات حتى الآن.",
    orderCount: "أحدث الطلبات (حتى ١٠٠)", status: "الحالة", customer: "العميل",
    phone: "الهاتف", address: "العنوان", items: "المنتجات",
    total: "الإجمالي عند الاستلام", delivery: "التوصيل", payment: "الدفع نقداً عند الاستلام",
    statuses: { new: "جديد", confirmed: "تم التأكيد", preparing: "قيد التجهيز", shipped: "تم الشحن", delivered: "تم التسليم", cancelled: "ملغي" },
  },
  tr: {
    announcement: "Epgyt Market sipariş yönetimi — yalnızca mağaza sahibine açıktır",
    languageLabel: "Dil seçimi", shopLink: "Mağazaya dön",
    dashboardKicker: "Mağaza yönetimi", dashboardTitle: "Siparişler",
    refresh: "Siparişleri yenile", logout: "Çıkış yap", adminToken: "Yönetici erişim anahtarı",
    signIn: "Güvenli giriş", tokenHelp: "Erişim anahtarı sunucudaki NILEMARKET_ADMIN_TOKEN ayarında bulunur.",
    privacyNote: "Müşteri bilgileri özeldir. Yönetim bağlantısını veya erişim anahtarını paylaşmayın.",
    adminFooter: "Mağazaya özel yönetim paneli.", loading: "Siparişler yükleniyor…",
    loginRequired: "Devam etmek için yönetici anahtarını girin.", loadError: "Siparişler yüklenemedi. Anahtarı ve sunucu bağlantısını kontrol edin.",
    updateError: "Sipariş durumu güncellenemedi.", empty: "Henüz sipariş yok.",
    orderCount: "Son siparişler (en fazla 100)", status: "Durum", customer: "Müşteri",
    phone: "Telefon", address: "Adres", items: "Ürünler",
    total: "Kapıda ödenecek toplam", delivery: "Teslimat", payment: "Kapıda nakit ödeme",
    statuses: { new: "Yeni", confirmed: "Onaylandı", preparing: "Hazırlanıyor", shipped: "Kargoda", delivered: "Teslim edildi", cancelled: "İptal edildi" },
  },
  en: {
    announcement: "Epgyt Market order management — private store-owner access",
    languageLabel: "Choose language", shopLink: "Back to shop",
    dashboardKicker: "Store management", dashboardTitle: "Orders",
    refresh: "Refresh orders", logout: "Sign out", adminToken: "Admin access token",
    signIn: "Sign in securely", tokenHelp: "The access token is configured on the server as NILEMARKET_ADMIN_TOKEN.",
    privacyNote: "Customer information is private. Do not share this dashboard URL or its access token.",
    adminFooter: "Private store management dashboard.", loading: "Loading orders…",
    loginRequired: "Enter the admin token to continue.", loadError: "Could not load orders. Check your token and server connection.",
    updateError: "Could not update order status.", empty: "No orders yet.",
    orderCount: "Recent orders (up to 100)", status: "Status", customer: "Customer",
    phone: "Phone", address: "Address", items: "Items",
    total: "Total due on delivery", delivery: "Delivery", payment: "Cash on delivery",
    statuses: { new: "New", confirmed: "Confirmed", preparing: "Preparing", shipped: "Shipped", delivered: "Delivered", cancelled: "Cancelled" },
  },
};

const currency = new Intl.NumberFormat(undefined, { style: "currency", currency: "EGP", maximumFractionDigits: 0 });
let language = "ar";
let accessToken = sessionStorage.getItem("epgyt-market-admin-token") || "";
let refreshTimer;
let storeName = "Epgyt Market";

function t(key) {
  return adminCopy[language][key];
}

function formatPrice(amount) {
  return currency.format(amount);
}

function applyLanguage() {
  document.documentElement.lang = language;
  document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
  document.title = language === "ar" ? `${storeName} — إدارة المتجر` : `${storeName} — Store dashboard`;
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.getElementById("admin-token").setAttribute("aria-label", t("adminToken"));
  document.querySelectorAll("[data-store-name]").forEach((element) => { element.textContent = storeName; });
  renderOrders(currentOrders);
}

let currentOrders = [];

function setMessage(message, isError = false) {
  const element = document.getElementById("admin-message");
  element.textContent = message;
  element.classList.toggle("error", isError);
}

async function loadOrders() {
  if (!accessToken) {
    setMessage(t("loginRequired"), true);
    return;
  }
  setMessage(t("loading"));
  try {
    const response = await fetch("/api/admin/orders", {
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Order request failed");
    const data = await response.json();
    currentOrders = data.orders;
    document.getElementById("admin-auth").hidden = true;
    document.getElementById("orders-section").hidden = false;
    document.getElementById("admin-logout").hidden = false;
    setMessage("");
    renderOrders(currentOrders);
    window.clearInterval(refreshTimer);
    refreshTimer = window.setInterval(loadOrders, 30_000);
  } catch {
    sessionStorage.removeItem("epgyt-market-admin-token");
    accessToken = "";
    document.getElementById("admin-auth").hidden = false;
    document.getElementById("orders-section").hidden = true;
    document.getElementById("admin-logout").hidden = true;
    setMessage(t("loadError"), true);
  }
}

function createText(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value;
  return element;
}

function renderOrders(orders) {
  const list = document.getElementById("orders-list");
  const summary = document.getElementById("order-summary");
  summary.replaceChildren(createText("span", "", `${t("orderCount")}: ${orders.length}`));
  if (!orders.length) {
    list.replaceChildren(createText("p", "orders-empty", t("empty")));
    return;
  }
  list.replaceChildren(...orders.map((order) => {
    const card = document.createElement("article");
    card.className = "order-card";
    const heading = document.createElement("div");
    heading.className = "order-card-heading";
    heading.append(
      createText("h2", "order-reference", `#${order.id}`),
      createText("time", "order-date", new Date(order.created_at).toLocaleString(language)),
    );
    const statusWrap = document.createElement("label");
    statusWrap.className = "order-status";
    statusWrap.append(createText("span", "", t("status")));
    const status = document.createElement("select");
    status.setAttribute("aria-label", `${t("status")} ${order.id}`);
    Object.entries(adminCopy[language].statuses).forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = value === order.status;
      status.append(option);
    });
    status.addEventListener("change", () => changeStatus(order.id, status.value));
    statusWrap.append(status);

    const customer = document.createElement("dl");
    customer.className = "order-customer";
    [
      [t("customer"), order.customer_name],
      [t("phone"), order.phone],
      [t("address"), `${governorateName(order.governorate)}, ${order.address}`],
    ].forEach(([label, value]) => {
      customer.append(createText("dt", "", label), createText("dd", "", value));
    });

    const lines = document.createElement("ul");
    lines.className = "order-lines";
    order.items.forEach((item) => {
      lines.append(createText("li", "", `${productName(item)} × ${item.quantity} — ${formatPrice(item.unit_price * item.quantity)}`));
    });
    const total = createText("strong", "order-total", `${t("total")}: ${formatPrice(order.total)}`);
    const delivery = createText("p", "order-delivery", `${t("delivery")}: ${formatPrice(order.delivery_fee)} · ${t("payment")}`);
    card.append(heading, statusWrap, customer, createText("h3", "order-items-heading", t("items")), lines, total, delivery);
    return card;
  }));
}

const GOVERNORATE_NAMES = {
  cairo: ["القاهرة", "Kahire", "Cairo"], giza: ["الجيزة", "Gize", "Giza"],
  alexandria: ["الإسكندرية", "İskenderiye", "Alexandria"],
  qalyubia: ["القليوبية", "Kalyubiye", "Qalyubia"],
  sharqia: ["الشرقية", "Şarkiye", "Sharqia"], dakahlia: ["الدقهلية", "Dekahliye", "Dakahlia"],
  gharbia: ["الغربية", "Garbiye", "Gharbia"], monufia: ["المنوفية", "Minufiye", "Monufia"],
  beheira: ["البحيرة", "Buhayra", "Beheira"],
  "kafr-el-sheikh": ["كفر الشيخ", "Kafr eş-Şeyh", "Kafr El Sheikh"],
  damietta: ["دمياط", "Dimyat", "Damietta"], "port-said": ["بورسعيد", "Port Said", "Port Said"],
  ismailia: ["الإسماعيلية", "İsmailiye", "Ismailia"], suez: ["السويس", "Süveyş", "Suez"],
  "north-sinai": ["شمال سيناء", "Kuzey Sina", "North Sinai"],
  "south-sinai": ["جنوب سيناء", "Güney Sina", "South Sinai"],
  "beni-suef": ["بني سويف", "Beni Süveyf", "Beni Suef"],
  fayoum: ["الفيوم", "Feyyum", "Fayoum"], minya: ["المنيا", "Minye", "Minya"],
  assiut: ["أسيوط", "Asyut", "Assiut"], sohag: ["سوهاج", "Sohag", "Sohag"],
  qena: ["قنا", "Kina", "Qena"], luxor: ["الأقصر", "Luksor", "Luxor"],
  aswan: ["أسوان", "Asvan", "Aswan"], "red-sea": ["البحر الأحمر", "Kızıldeniz", "Red Sea"],
  "new-valley": ["الوادي الجديد", "Yeni Vadi", "New Valley"],
  matrouh: ["مطروح", "Matruh", "Matrouh"],
};

const PRODUCT_NAMES = {
  "ceramic-vase": ["مزهرية سيراميك يدوية", "El Yapımı Seramik Vazo", "Handmade Ceramic Vase"],
  "woven-bag": ["حقيبة يد منسوجة", "Hasır Günlük Çanta", "Woven Everyday Tote"],
  "linen-shirt": ["قميص كتان ناعم", "Yumuşak Keten Gömlek", "Soft Linen Shirt"],
  "face-oil": ["زيت وجه نباتي", "Bitkisel Yüz Yağı", "Botanical Face Oil"],
  "woven-bowl": ["وعاء من سعف النخيل", "Palmiye Örgü Kase", "Palm-Woven Catchall"],
  "gold-earrings": ["أقراط نحاسية منحوتة", "Şekilli Pirinç Küpe", "Sculpted Brass Hoops"],
  "cotton-shirt": ["قميص قطني يومي", "Günlük Pamuklu Tişört", "Everyday Cotton Tee"],
  "body-butter": ["بلسم مغذٍ للجسم", "Besleyici Vücut Balmı", "Nourishing Body Balm"],
};

function governorateName(code) {
  return GOVERNORATE_NAMES[code]?.[["ar", "tr", "en"].indexOf(language)] || code;
}

function productName(item) {
  return item.names?.[language] || PRODUCT_NAMES[item.id]?.[["ar", "tr", "en"].indexOf(language)] || item.name;
}

async function changeStatus(orderId, status) {
  try {
    const response = await fetch(`/api/admin/orders/${encodeURIComponent(orderId)}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!response.ok) throw new Error("Status update failed");
    await loadOrders();
  } catch {
    setMessage(t("updateError"), true);
  }
}

document.getElementById("language-select").addEventListener("change", (event) => {
  language = event.target.value;
  applyLanguage();
});
document.getElementById("admin-login").addEventListener("submit", (event) => {
  event.preventDefault();
  accessToken = document.getElementById("admin-token").value.trim();
  sessionStorage.setItem("epgyt-market-admin-token", accessToken);
  loadOrders();
});
document.getElementById("refresh-orders").addEventListener("click", loadOrders);
document.getElementById("admin-logout").addEventListener("click", () => {
  window.clearInterval(refreshTimer);
  sessionStorage.removeItem("epgyt-market-admin-token");
  accessToken = "";
  currentOrders = [];
  document.getElementById("admin-auth").hidden = false;
  document.getElementById("orders-section").hidden = true;
  document.getElementById("admin-logout").hidden = true;
  document.getElementById("admin-token").value = "";
  setMessage(t("loginRequired"), false);
});
document.getElementById("year").textContent = String(new Date().getFullYear());
document.getElementById("admin-token").value = accessToken;
applyLanguage();
fetch("/api/config", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error("Store configuration request failed");
    return response.json();
  })
  .then((config) => {
    if (typeof config.store_name !== "string") throw new Error("Store name is missing");
    storeName = config.store_name;
    applyLanguage();
  })
  .catch(() => setMessage(t("loadError"), true));
if (accessToken) loadOrders();
