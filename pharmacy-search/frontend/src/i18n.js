/**
 * Locale strings, Vietnamese first.
 *
 * The premise of this project is that a Vietnamese speaker can type a product
 * name badly - in Telex, in VNI, half-accented - and still find it. Shipping
 * that behind an English interface asked those users to read a second language
 * to reach a feature built for their first. So vi is the default and en is the
 * fallback, not the other way round.
 *
 * Only the shopper-facing views are translated. The admin console is a staff
 * tool for one pharmacy and is deliberately left in English rather than
 * half-translated - a mixed-language screen is worse than a consistent one.
 *
 * Keys are flat and dotted. A missing key falls through to English and then to
 * the key itself, so an untranslated string is visible rather than blank.
 */

const LOCALE_KEY = 'pharmacy-search-locale';

export const LOCALES = [
  { code: 'vi', label: 'Tiếng Việt' },
  { code: 'en', label: 'English' },
];

const vi = {
  'brand.tagline': 'Tìm kiếm chịu lỗi chính tả — luôn ưu tiên độ chính xác.',
  'a11y.skipToContent': 'Bỏ qua, đến nội dung chính',
  'a11y.language': 'Ngôn ngữ',
  'a11y.rating': '{avg} trên 5 sao',

  'nav.search': 'Tìm kiếm',
  'nav.browse': 'Danh mục',
  'nav.wishlist': 'Yêu thích',
  'nav.cart': 'Giỏ hàng',
  'nav.admin': 'Quản trị',
  'nav.signIn': 'Đăng nhập',

  'common.loading': 'Đang tải…',
  'common.remove': 'Xóa',
  'common.apply': 'Áp dụng',
  'common.free': 'Miễn phí',
  'common.estimated': 'ước tính',
  'common.inStock': 'Còn {n} sản phẩm',
  'common.outOfStock': 'Hết hàng',
  'common.priceUnavailable': 'Chưa có giá',
  'common.rxShort': 'Kê đơn',
  'common.rxOnly': 'Thuốc kê đơn',
  'common.moveToCart': 'Chuyển vào giỏ',
  'common.noRating': 'Chưa có đánh giá',
  'common.signInTo.cart': 'Vui lòng <a href="#/account">đăng nhập</a> để xem giỏ hàng.',
  'common.signInTo.wishlist': 'Vui lòng <a href="#/account">đăng nhập</a> để xem danh sách yêu thích.',
  'common.signInTo.checkout': 'Vui lòng <a href="#/account">đăng nhập</a> để thanh toán.',
  'common.signInTo.order': 'Vui lòng <a href="#/account">đăng nhập</a> để xem đơn hàng này.',

  'search.placeholder': 'Tìm sản phẩm hoặc hoạt chất…',
  'search.showingResultsFor': 'Đang hiển thị kết quả cho',
  'search.searchLiterally': 'tìm đúng nguyên văn “{q}”',
  'search.didYouMean': 'Có phải bạn muốn tìm?',
  'search.noResults': 'Không có kết quả cho <strong>{q}</strong> — truy vấn này đã được ghi lại để xem xét.',
  'search.debugTitle': 'Chi tiết kỹ thuật',
  'search.debug.token': 'từ',
  'search.debug.status': 'trạng thái',
  'search.debug.candidates': 'ứng viên',
  'search.debug.summary': 'quyết định=<strong>{decision}</strong> · độ trễ={latency}ms',
  'search.preset.typo': 'lỗi gõ → tự sửa',
  'search.preset.phonetic': 'cách viết theo âm',
  'search.preset.dose': 'hàm lượng được giữ nguyên',
  'search.preset.ambiguous': 'nhập nhằng → gợi ý',
  'search.preset.none': 'không có kết quả',

  'browse.filterByName': 'Lọc theo tên…',
  'browse.category': 'Danh mục',
  'browse.allCategories': 'Tất cả danh mục',
  'browse.brand': 'Thương hiệu',
  'browse.allBrands': 'Tất cả thương hiệu',
  'browse.priceRange': 'Khoảng giá (₫)',
  'browse.min': 'Thấp nhất',
  'browse.max': 'Cao nhất',
  'browse.minRating': 'Đánh giá tối thiểu',
  'browse.anyRating': 'Mọi mức đánh giá',
  'browse.ratingAndUp': 'Từ {n}★',
  'browse.inStockOnly': 'Chỉ sản phẩm còn hàng',
  'browse.clearFilters': 'Xóa bộ lọc',
  'browse.empty': 'Không có sản phẩm nào khớp bộ lọc này.',
  'browse.quickAdd': '+ Thêm vào giỏ',
  'browse.quickAdded': 'Đã thêm ✓',
  'browse.prev': '← Trang trước',
  'browse.next': 'Trang sau →',
  'browse.pagerStatus': 'Trang {page}/{total} · {count} sản phẩm',
  'browse.sort.name': 'Theo bảng chữ cái',
  'browse.sort.price_asc': 'Giá: thấp đến cao',
  'browse.sort.price_desc': 'Giá: cao đến thấp',
  'browse.sort.newest': 'Mới nhất',
  'browse.sort.top_rated': 'Đánh giá cao nhất',
  'browse.sort.best_selling': 'Bán chạy nhất',
  'browse.cat.thuoc': 'Thuốc',
  'browse.cat.supplements': 'Thực phẩm chức năng',
  'browse.cat.cosmeceuticals': 'Dược mỹ phẩm',
  'browse.cat.personalCare': 'Chăm sóc cá nhân',
  'browse.cat.devices': 'Trang thiết bị y tế',

  'product.backToBrowse': '← Quay lại danh mục',
  'product.notFound': 'Không tìm thấy sản phẩm.',
  'product.sku': 'Mã SKU {sku}',
  'product.brandEstimated': '(ước tính)',
  'product.rxRequired': 'Cần đơn thuốc',
  'product.reviewCount': '({n} đánh giá)',
  'product.estimatedPrice': 'giá tạm tính',
  'product.addToCart': 'Thêm vào giỏ',
  'product.saveToWishlist': 'Lưu vào yêu thích',
  'product.addedToCart': 'Đã thêm vào giỏ hàng.',
  'product.savedToWishlist': 'Đã lưu vào danh sách yêu thích.',
  'product.ingredients': 'Thành phần',
  'product.reviews': 'Đánh giá',
  'product.noReviews': 'Chưa có đánh giá nào.',
  'product.verifiedPurchase': 'đã mua hàng',
  'product.signInToReview': '<a href="#/account">Đăng nhập</a> để viết đánh giá.',
  'product.buyersOnly': 'Chỉ khách hàng đã đặt mua sản phẩm này mới có thể đánh giá.',
  'product.yourRating': 'Đánh giá của bạn',
  'product.rating.5': '5 — Rất tốt',
  'product.rating.4': '4 — Tốt',
  'product.rating.3': '3 — Tạm ổn',
  'product.rating.2': '2 — Kém',
  'product.rating.1': '1 — Rất kém',
  'product.comment': 'Nhận xét (không bắt buộc)',
  'product.submitReview': 'Gửi đánh giá',

  'cart.title': 'Giỏ hàng của bạn',
  'cart.summary': 'Tóm tắt đơn hàng',
  'cart.subtotal': 'Tạm tính',
  'cart.total': 'Tổng cộng',
  'cart.discount': 'Giảm giá ({code})',
  'cart.discountCode': 'Mã giảm giá',
  'cart.empty': 'Giỏ hàng của bạn đang trống.',
  'cart.savedForLater': 'Để dành mua sau',
  'cart.saveForLater': 'Để dành mua sau',
  'cart.qty': 'SL: {n}',
  'cart.checkout': 'Tiến hành thanh toán',

  'wishlist.title': 'Danh sách yêu thích',
  'wishlist.empty': 'Chưa lưu sản phẩm nào — xem <a href="#/browse">danh mục</a> và lưu lại thứ bạn quan tâm.',

  'checkout.title': 'Thanh toán',
  'checkout.emptyCart': 'Giỏ hàng của bạn đang trống — <a href="#/browse">xem danh mục</a> trước đã.',
  'checkout.needAddress': 'Hãy thêm địa chỉ giao hàng trong <a href="#/account">tài khoản</a> trước khi thanh toán.',
  'checkout.address': 'Địa chỉ giao hàng',
  'checkout.shipping': 'Phương thức giao hàng',
  'checkout.payment': 'Phương thức thanh toán',
  'checkout.notConnected': 'chưa kết nối — chỉ để minh họa',
  'checkout.paymentNote': 'Hiện chỉ có thanh toán khi nhận hàng (COD) hoàn tất được đơn hàng. Các phương thức khác chỉ minh họa luồng thanh toán; không có khoản nào bị trừ vì chưa tích hợp VNPay/Momo.',
  'checkout.rxTitle': 'Cần đơn thuốc',
  'checkout.rxNote': 'Các sản phẩm sau là thuốc kê đơn: <strong>{items}</strong>. Vui lòng nhập mã số trên đơn thuốc của bạn. Dược sĩ sẽ duyệt mọi đơn hàng có thuốc kê đơn trước khi giao — đơn của bạn sẽ được tạo và giữ lại cho đến khi duyệt xong.',
  'checkout.rxReference': 'Mã số đơn thuốc',
  'checkout.rxPlaceholder': 'ví dụ: số hiệu phiếu của phòng khám',
  'checkout.shippingFee': 'Phí giao hàng',
  'checkout.placeOrder': 'Đặt hàng',
  'checkout.placeOrderForReview': 'Đặt hàng chờ duyệt',
  'checkout.placing': 'Đang đặt hàng…',

  'order.backToAccount': '← Quay lại tài khoản',
  'order.notFound': 'Không tìm thấy đơn hàng.',
  'order.title': 'Đơn hàng #{id}',
  'order.shippingAndPayment': 'Giao hàng {shipping} · {payment}',
  'order.items': 'Sản phẩm',
  'order.each': '/sản phẩm',
  'order.wasEstimated': 'giá từng là ước tính',
  'order.prescriptionTitle': 'Đơn thuốc: {status}',
  'order.status.placed': 'Đã đặt',
  'order.status.pending_payment': 'Chờ thanh toán (demo)',
  'order.status.awaiting_prescription': 'Chờ dược sĩ duyệt',
  'order.status.shipped': 'Đang giao',
  'order.status.delivered': 'Đã giao',
  'order.status.cancelled': 'Đã hủy',
  'order.rx.pending_review': 'Đơn hàng này có thuốc kê đơn. Dược sĩ đang kiểm tra đơn thuốc của bạn; chưa có gì được giao cho đến khi việc kiểm tra hoàn tất.',
  'order.rx.approved': 'Đơn thuốc của bạn đã được dược sĩ duyệt và đơn hàng đang được xử lý.',
  'order.rx.rejected': 'Dược sĩ không thể duyệt đơn thuốc cho đơn hàng này nên đơn đã bị hủy và bạn không bị trừ khoản nào. Hãy liên hệ với chúng tôi nếu bạn cho rằng đây là nhầm lẫn.',
  'order.rxStatus.pending_review': 'đang chờ duyệt',
  'order.rxStatus.approved': 'đã duyệt',
  'order.rxStatus.rejected': 'bị từ chối',
  'order.reference': 'Mã số: {ref}',

  'account.signIn': 'Đăng nhập',
  'account.register': 'Đăng ký',
  'account.email': 'Email',
  'account.password': 'Mật khẩu',
  'account.name': 'Họ tên',
  'account.createAccount': 'Tạo tài khoản',
  'account.forgot': 'Quên mật khẩu?',
  'account.forgotHint': 'Nhập email của bạn; nếu email đó có tài khoản, một liên kết đặt lại sẽ được tạo.',
  'account.sendReset': 'Gửi liên kết đặt lại',
  'account.resetSent': 'Nếu email đó có tài khoản, liên kết đặt lại đã được gửi.',
  'account.resetDevToken': 'Chế độ phát triển (chưa cấu hình dịch vụ email) — mã đặt lại: {token}',
  'account.profile': 'Hồ sơ',
  'account.saveProfile': 'Lưu hồ sơ',
  'account.saved': 'Đã lưu.',
  'account.signOut': 'Đăng xuất',
  'account.changePassword': 'Đổi mật khẩu',
  'account.currentPassword': 'Mật khẩu hiện tại',
  'account.newPassword': 'Mật khẩu mới',
  'account.updatePassword': 'Cập nhật mật khẩu',
  'account.passwordUpdated': 'Đã cập nhật mật khẩu.',
  'account.addresses': 'Địa chỉ giao hàng',
  'account.label': 'Nhãn',
  'account.labelPlaceholder': 'Nhà riêng',
  'account.recipient': 'Tên người nhận',
  'account.phone': 'Số điện thoại',
  'account.line1': 'Địa chỉ',
  'account.city': 'Tỉnh/Thành phố',
  'account.setDefault': 'Đặt làm mặc định',
  'account.addAddress': 'Thêm địa chỉ',
  'account.noAddresses': 'Chưa có địa chỉ nào.',
  'account.default': 'mặc định',
  'account.orderHistory': 'Lịch sử đơn hàng',
  'account.noOrders': 'Chưa có đơn hàng nào.',
  'account.orderLabel': 'Đơn hàng #{id}',
  'account.orderSummary': '{n} sản phẩm · {total}',
};

const en = {
  'brand.tagline': 'Typo-tolerant product search — precision over recall, always.',
  'a11y.skipToContent': 'Skip to content',
  'a11y.language': 'Language',
  'a11y.rating': '{avg} out of 5',

  'nav.search': 'Search',
  'nav.browse': 'Browse',
  'nav.wishlist': 'Wishlist',
  'nav.cart': 'Cart',
  'nav.admin': 'Admin',
  'nav.signIn': 'Sign in',

  'common.loading': 'Loading…',
  'common.remove': 'Remove',
  'common.apply': 'Apply',
  'common.free': 'Free',
  'common.estimated': 'estimated',
  'common.inStock': '{n} in stock',
  'common.outOfStock': 'Out of stock',
  'common.priceUnavailable': 'Price unavailable',
  'common.rxShort': 'Rx',
  'common.rxOnly': 'Prescription only',
  'common.moveToCart': 'Move to cart',
  'common.noRating': 'No ratings yet',
  'common.signInTo.cart': 'Please <a href="#/account">sign in</a> to view your cart.',
  'common.signInTo.wishlist': 'Please <a href="#/account">sign in</a> to view your wishlist.',
  'common.signInTo.checkout': 'Please <a href="#/account">sign in</a> to check out.',
  'common.signInTo.order': 'Please <a href="#/account">sign in</a> to view this order.',

  'search.placeholder': 'Search a product or ingredient…',
  'search.showingResultsFor': 'Showing results for',
  'search.searchLiterally': 'search for “{q}” instead',
  'search.didYouMean': 'Did you mean one of these?',
  'search.noResults': 'No results for <strong>{q}</strong> — this query was logged for review.',
  'search.debugTitle': 'Debug details',
  'search.debug.token': 'token',
  'search.debug.status': 'status',
  'search.debug.candidates': 'candidates',
  'search.debug.summary': 'decision=<strong>{decision}</strong> · latency={latency}ms',
  'search.preset.typo': 'typo → auto-correct',
  'search.preset.phonetic': 'phonetic spelling',
  'search.preset.dose': 'dose is protected',
  'search.preset.ambiguous': 'ambiguous → did you mean',
  'search.preset.none': 'no results',

  'browse.filterByName': 'Filter by name…',
  'browse.category': 'Category',
  'browse.allCategories': 'All categories',
  'browse.brand': 'Brand',
  'browse.allBrands': 'All brands',
  'browse.priceRange': 'Price range (₫)',
  'browse.min': 'Min',
  'browse.max': 'Max',
  'browse.minRating': 'Minimum rating',
  'browse.anyRating': 'Any rating',
  'browse.ratingAndUp': '{n}★ & up',
  'browse.inStockOnly': 'In stock only',
  'browse.clearFilters': 'Clear filters',
  'browse.empty': 'No products match this filter.',
  'browse.quickAdd': '+ Add to cart',
  'browse.quickAdded': 'Added ✓',
  'browse.prev': '← Previous',
  'browse.next': 'Next →',
  'browse.pagerStatus': 'Page {page} of {total} · {count} products',
  'browse.sort.name': 'Alphabetical',
  'browse.sort.price_asc': 'Price: low to high',
  'browse.sort.price_desc': 'Price: high to low',
  'browse.sort.newest': 'Newest',
  'browse.sort.top_rated': 'Top rated',
  'browse.sort.best_selling': 'Best selling',
  'browse.cat.thuoc': 'Medicine (thuốc)',
  'browse.cat.supplements': 'Supplements (thực phẩm chức năng)',
  'browse.cat.cosmeceuticals': 'Cosmeceuticals (dược mỹ phẩm)',
  'browse.cat.personalCare': 'Personal care (chăm sóc cá nhân)',
  'browse.cat.devices': 'Medical devices (trang thiết bị y tế)',

  'product.backToBrowse': '← Back to browse',
  'product.notFound': 'Product not found.',
  'product.sku': 'SKU {sku}',
  'product.brandEstimated': '(estimated)',
  'product.rxRequired': 'Prescription required',
  'product.reviewCount': '({n} reviews)',
  'product.estimatedPrice': 'estimated placeholder price',
  'product.addToCart': 'Add to cart',
  'product.saveToWishlist': 'Save to wishlist',
  'product.addedToCart': 'Added to cart.',
  'product.savedToWishlist': 'Saved to wishlist.',
  'product.ingredients': 'Ingredients',
  'product.reviews': 'Reviews',
  'product.noReviews': 'No reviews yet.',
  'product.verifiedPurchase': 'verified purchase',
  'product.signInToReview': '<a href="#/account">Sign in</a> to write a review.',
  'product.buyersOnly': 'Only customers who have ordered this product can review it.',
  'product.yourRating': 'Your rating',
  'product.rating.5': '5 — Excellent',
  'product.rating.4': '4 — Good',
  'product.rating.3': '3 — Okay',
  'product.rating.2': '2 — Poor',
  'product.rating.1': '1 — Bad',
  'product.comment': 'Comment (optional)',
  'product.submitReview': 'Submit review',

  'cart.title': 'Your cart',
  'cart.summary': 'Order summary',
  'cart.subtotal': 'Subtotal',
  'cart.total': 'Total',
  'cart.discount': 'Discount ({code})',
  'cart.discountCode': 'Discount code',
  'cart.empty': 'Your cart is empty.',
  'cart.savedForLater': 'Saved for later',
  'cart.saveForLater': 'Save for later',
  'cart.qty': 'Qty: {n}',
  'cart.checkout': 'Proceed to checkout',

  'wishlist.title': 'Your wishlist',
  'wishlist.empty': 'Nothing saved yet — browse the <a href="#/browse">catalog</a> and save something for later.',

  'checkout.title': 'Checkout',
  'checkout.emptyCart': 'Your cart is empty — <a href="#/browse">browse the catalog</a> first.',
  'checkout.needAddress': 'Add a shipping address in your <a href="#/account">account</a> before checking out.',
  'checkout.address': 'Shipping address',
  'checkout.shipping': 'Shipping method',
  'checkout.payment': 'Payment method',
  'checkout.notConnected': 'not connected — demo only',
  'checkout.paymentNote': 'Cash on delivery is the only payment method that actually completes an order right now. The others show what the flow would look like, but nothing is charged — there is no VNPay/Momo integration behind them.',
  'checkout.rxTitle': 'Prescription required',
  'checkout.rxNote': 'These items are prescription-only: <strong>{items}</strong>. Enter the reference number from your prescription. A pharmacist reviews every order containing them before it ships — your order will be placed and held until that review is done.',
  'checkout.rxReference': 'Prescription reference',
  'checkout.rxPlaceholder': 'e.g. clinic document number',
  'checkout.shippingFee': 'Shipping',
  'checkout.placeOrder': 'Place order',
  'checkout.placeOrderForReview': 'Place order for review',
  'checkout.placing': 'Placing order…',

  'order.backToAccount': '← Back to account',
  'order.notFound': 'Order not found.',
  'order.title': 'Order #{id}',
  'order.shippingAndPayment': '{shipping} shipping · {payment}',
  'order.items': 'Items',
  'order.each': 'each',
  'order.wasEstimated': 'was estimated',
  'order.prescriptionTitle': 'Prescription {status}',
  'order.status.placed': 'Placed',
  'order.status.pending_payment': 'Awaiting payment (demo)',
  'order.status.awaiting_prescription': 'Held for pharmacist review',
  'order.status.shipped': 'Shipped',
  'order.status.delivered': 'Delivered',
  'order.status.cancelled': 'Cancelled',
  'order.rx.pending_review': 'This order contains prescription-only medicine. A pharmacist is reviewing your prescription; nothing ships until that review is complete.',
  'order.rx.approved': 'Your prescription was approved by a pharmacist and this order is being processed.',
  'order.rx.rejected': 'A pharmacist could not approve the prescription for this order, so it was cancelled and nothing was charged. Please contact us if you think this was a mistake.',
  'order.rxStatus.pending_review': 'pending review',
  'order.rxStatus.approved': 'approved',
  'order.rxStatus.rejected': 'rejected',
  'order.reference': 'Reference: {ref}',

  'account.signIn': 'Sign in',
  'account.register': 'Register',
  'account.email': 'Email',
  'account.password': 'Password',
  'account.name': 'Name',
  'account.createAccount': 'Create account',
  'account.forgot': 'Forgot your password?',
  'account.forgotHint': 'Enter your email and, if there is an account, a reset link will be issued.',
  'account.sendReset': 'Send reset link',
  'account.resetSent': 'If that email has an account, a reset link was sent.',
  'account.resetDevToken': 'Dev mode (no email service configured yet) — reset token: {token}',
  'account.profile': 'Profile',
  'account.saveProfile': 'Save profile',
  'account.saved': 'Saved.',
  'account.signOut': 'Sign out',
  'account.changePassword': 'Change password',
  'account.currentPassword': 'Current password',
  'account.newPassword': 'New password',
  'account.updatePassword': 'Update password',
  'account.passwordUpdated': 'Password updated.',
  'account.addresses': 'Shipping addresses',
  'account.label': 'Label',
  'account.labelPlaceholder': 'Home',
  'account.recipient': 'Recipient name',
  'account.phone': 'Phone',
  'account.line1': 'Address line',
  'account.city': 'City',
  'account.setDefault': 'Set as default',
  'account.addAddress': 'Add address',
  'account.noAddresses': 'No saved addresses yet.',
  'account.default': 'default',
  'account.orderHistory': 'Order history',
  'account.noOrders': 'No orders yet.',
  'account.orderLabel': 'Order #{id}',
  'account.orderSummary': '{n} items · {total}',
};

const STRINGS = { vi, en };

let current = readLocale();

function readLocale() {
  try {
    const stored = localStorage.getItem(LOCALE_KEY);
    if (stored && STRINGS[stored]) return stored;
  } catch (err) {
    // Private mode, or site data blocked. Fall through to the default.
  }
  // Vietnamese unless the browser clearly prefers English and not Vietnamese.
  // The catalogue is Vietnamese and so is the typing problem this app solves.
  const preferred = (navigator.languages || [navigator.language || ''])
    .map((l) => String(l).toLowerCase());
  return preferred.some((l) => l.startsWith('en')) && !preferred.some((l) => l.startsWith('vi'))
    ? 'en'
    : 'vi';
}

export function getLocale() {
  return current;
}

export function setLocale(code) {
  if (!STRINGS[code]) return;
  current = code;
  try {
    localStorage.setItem(LOCALE_KEY, code);
  } catch (err) {
    // Not persisting is survivable; the session still switches.
  }
  applyDocumentLang();
}

export function applyDocumentLang() {
  document.documentElement.lang = current;
}

/**
 * Look up `key` and substitute {placeholders}.
 *
 * Values are inserted raw, because several strings intentionally carry markup
 * (a sign-in link, a <strong> around the corrected query). Callers pass
 * already-escaped text - the same contract the view templates already follow
 * with escapeHtml.
 */
export function t(key, vars) {
  let value = STRINGS[current][key];
  if (value === undefined) value = STRINGS.en[key];
  if (value === undefined) return key;
  if (!vars) return value;
  return value.replace(/\{(\w+)\}/g, (match, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match);
}
