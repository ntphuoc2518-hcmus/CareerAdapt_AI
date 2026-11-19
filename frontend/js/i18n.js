/**
 * CareerAdapt AI - lightweight internationalisation (Vietnamese / English).
 *
 * Markup:  data-i18n="key"                 -> textContent
 *          data-i18n-placeholder="key"     -> placeholder
 *          data-i18n-aria-label="key"      -> aria-label
 *          data-i18n-title="key"           -> title
 * Script:  i18n.t("key", { name: "An" })   -> "{name}" placeholders are filled
 *
 * The choice is remembered in this browser and, once signed in, saved to the account.
 */
(function () {
    const STORAGE_KEY = "careeradapt_lang";
    const SUPPORTED = ["vi", "en"];

    const MESSAGES = {
        vi: {
            "lang.label": "Ngôn ngữ",
            "lang.vi": "Tiếng Việt",
            "lang.en": "English",
            "theme.toggle": "Đổi giao diện sáng, tối, theo hệ thống",
            "theme.label": "Giao diện",
            "theme.light": "Sáng",
            "theme.dark": "Tối",
            "theme.system": "Theo hệ thống",

            // Login page
            "login.pageTitle": "Đăng nhập · CareerAdapt AI",
            "login.brandTagline": "Hiểu đúng năng lực · Vững bước tương lai",
            "login.eyebrow": "KHÔNG GIAN HỌC TẬP CÁ NHÂN",
            "login.heroLine1": "Tiến bộ rõ ràng.",
            "login.heroLine2": "Cơ hội rộng mở.",
            "login.heroBody": "Đánh giá năng lực bằng bài làm thực tế, hiểu khoảng cách kỹ năng và theo sát lộ trình Data Analyst của riêng bạn.",
            "login.proof1Title": "Học tập có bằng chứng",
            "login.proof1Body": "Kỹ năng được xác nhận qua bài đánh giá",
            "login.proof2Title": "Lộ trình theo mục tiêu",
            "login.proof2Body": "Theo dõi tiến độ theo từng tuần",
            "login.proof3Title": "Dữ liệu do bạn quản lý",
            "login.proof3Body": "Tải về hoặc xóa hồ sơ của mình bất cứ lúc nào",
            "login.capsLock": "Caps Lock đang bật",
            "login.bot.hello": "Chào bạn! Mình là trợ lý CareerAdapt AI. Đăng nhập để mình đồng hành tiếp nhé.",
            "login.bot.register": "Tạo tài khoản để mình giúp bạn đo năng lực và lập lộ trình học.",
            "login.bot.forgot": "Không sao đâu! Nhập email đã đăng ký để nhận liên kết đặt lại.",
            "login.bot.reset": "Chọn một mật khẩu mới thật chắc chắn nhé.",
            "login.bot.email": "Nhập email bạn đã dùng khi đăng ký nhé.",
            "login.bot.emailNew": "Dùng email bạn thường xem, để lấy lại mật khẩu khi cần.",
            "login.bot.emailForgot": "Liên kết đặt lại sẽ được gửi tới email này nếu nó đã đăng ký.",
            "login.bot.name": "Tên này sẽ hiện trên hồ sơ của bạn.",
            "login.bot.password": "Mình nhắm mắt rồi, bạn cứ yên tâm nhập mật khẩu nhé.",
            "login.bot.peek": "Mật khẩu đang hiện đó, nhớ để ý người xung quanh nhé.",
            "login.bot.caps": "Caps Lock đang bật đó, kiểm tra lại chữ hoa nhé.",
            "login.bot.checking": "Đợi mình kiểm tra một chút…",
            "login.bot.error": "Có gì đó chưa đúng. Xem thông báo bên dưới rồi thử lại nhé.",
            "login.bot.success": "Tuyệt! Xem thông báo bên dưới để làm bước tiếp theo nhé.",
            "login.footerSlogan": "Học đúng trọng tâm, tiến xa hơn.",
            "landing.signIn": "Đăng nhập",
            "landing.eyebrow": "DÀNH CHO SINH VIÊN HƯỚNG TỚI DATA ANALYST",
            "landing.title": "Biết chính xác bạn còn cách JD bao xa.",
            "landing.lead": "CareerAdapt AI đo năng lực bằng bài làm thật, so với JD bạn chọn, rồi lập lộ trình học theo tuần để thu hẹp khoảng cách.",
            "landing.start": "Bắt đầu đo năng lực",
            "landing.how": "Xem cách hoạt động",
            "landing.point1": "Điểm do máy chủ chấm bằng test case và rubric",
            "landing.point2": "AI chỉ nhận xét, không tạo điểm",
            "landing.point3": "Mức tự khai không được tính là năng lực",
            "landing.howTitle": "Năm bước, một quy trình",
            "landing.step1Title": "Khai báo kỹ năng",
            "landing.step1Body": "Bạn tự khai mức hiện tại để so sánh với kết quả bài làm; độ khó theo mức JD yêu cầu.",
            "landing.step2Title": "Chọn JD mục tiêu",
            "landing.step2Body": "Dùng JD trong thư viện có nguồn, hoặc dán JD bạn muốn ứng tuyển.",
            "landing.step3Title": "Làm bài kiểm tra",
            "landing.step3Body": "SQL, Python, chất lượng dữ liệu, trực quan hóa và viết báo cáo trên dữ liệu mẫu.",
            "landing.step4Title": "Xem khoảng cách",
            "landing.step4Body": "Từng kỹ năng: mức đã xác thực, mức JD yêu cầu và lý do.",
            "landing.step5Title": "Học theo lộ trình",
            "landing.step5Body": "Lộ trình theo tuần với học liệu đã duyệt và bài kiểm tra lại.",
            "landing.getTitle": "Bạn nhận được gì",
            "landing.card1Title": "Trình độ có bằng chứng",
            "landing.card1Body": "Bốn mức từ Chưa bắt đầu đến Sẵn sàng đầu nghề. Mỗi mức chỉ được ghi nhận khi có bài làm chứng minh.",
            "landing.card2Title": "Mức độ cạnh tranh",
            "landing.card2Body": "Biết mình đứng thứ mấy trong số người đã làm cùng bài kiểm tra. Bảng xếp hạng ẩn danh, bạn tự chọn có hiện tên hay không.",
            "landing.card3Title": "Lương tham khảo có nguồn",
            "landing.card3Body": "Lương trung vị theo năm kinh nghiệm từ báo cáo thị trường công khai, kèm đường dẫn nguồn và ngày kiểm tra.",
            "landing.card4Title": "Nguồn của từng kết quả",
            "landing.card4Body": "Khung kỹ năng, mức JD, cách chấm và học liệu đều ghi rõ lấy từ đâu.",
            "landing.closeTitle": "Sẵn sàng biết mình đang ở đâu?",
            "landing.closeCta": "Tạo tài khoản hoặc đăng nhập",
            "landing.note": "Kết quả chỉ phản ánh các bài đã đo, không phải chứng chỉ nghề hay bảo đảm được tuyển.",
            "login.about": "Tìm hiểu về CareerAdapt AI",
            "login.panelLabel": "Đăng nhập hoặc tạo tài khoản",
            "login.tabsLabel": "Tùy chọn tài khoản",
            "login.tabLogin": "Đăng nhập",
            "login.tabRegister": "Tạo tài khoản",
            "login.titleLogin": "Chào mừng bạn trở lại",
            "login.subtitleLogin": "Đăng nhập để tiếp tục lộ trình học tập.",
            "login.titleRegister": "Bắt đầu hành trình của bạn",
            "login.subtitleRegister": "Tạo tài khoản học viên để lưu tiến độ riêng.",
            "login.titleForgot": "Quên mật khẩu?",
            "login.subtitleForgot": "Nhập email đã đăng ký, chúng tôi sẽ gửi liên kết đặt lại mật khẩu.",
            "login.titleReset": "Đặt mật khẩu mới",
            "login.subtitleReset": "Chọn mật khẩu mới cho tài khoản của bạn.",
            "login.email": "Email",
            "login.emailPlaceholder": "tenban@example.com",
            "login.password": "Mật khẩu",
            "login.passwordPlaceholder": "Nhập mật khẩu",
            "login.forgotLink": "Quên mật khẩu?",
            "login.submitLogin": "Đăng nhập",
            "login.fullName": "Họ và tên",
            "login.fullNamePlaceholder": "Nguyễn Minh Anh",
            "login.createPassword": "Tạo mật khẩu",
            "login.createPasswordPlaceholder": "Tạo mật khẩu mạnh",
            "login.confirmPassword": "Nhập lại mật khẩu",
            "login.confirmPasswordPlaceholder": "Nhập lại mật khẩu",
            "login.submitRegister": "Tạo tài khoản học viên",
            "login.submitForgot": "Gửi liên kết đặt lại",
            "login.newPassword": "Mật khẩu mới",
            "login.submitReset": "Lưu mật khẩu mới",
            "login.backToLogin": "← Quay lại đăng nhập",
            "login.securityNote": "Phiên đăng nhập được bảo vệ. Thông tin mật khẩu không được lưu dưới dạng văn bản.",
            "login.adminHelp": "Cần quyền quản trị? Liên hệ người quản lý hệ thống để được cấp tài khoản.",
            "login.footer": "Nền tảng học tập cá nhân hóa",
            "login.processing": "Đang xử lý…",
            "login.show": "Hiện",
            "login.hide": "Ẩn",
            "login.showPassword": "Hiện mật khẩu",
            "login.hidePassword": "Ẩn mật khẩu",
            "login.registered": "Đã tạo tài khoản cho {email}. Hãy đăng nhập bằng email và mật khẩu vừa tạo.",
            "login.forgotSent": "Nếu email này đã đăng ký, một liên kết đặt lại mật khẩu (hiệu lực 30 phút) đã được gửi tới hộp thư.",
            "login.resetDone": "Đã đặt mật khẩu mới. Hãy đăng nhập lại; các phiên đăng nhập cũ đã được đăng xuất.",
            "login.csrfInit": "Không thể khởi tạo phiên bảo mật. Hãy tải lại trang.",
            "login.network": "Không thể kết nối đến máy chủ.",
            "login.fixFields": "Vui lòng hoàn thành các trường được đánh dấu.",

            // Password checklist
            "pw.title": "Mật khẩu còn cần:",
            "pw.length": "Ít nhất 8 ký tự",
            "pw.upper": "Ít nhất 1 chữ cái in hoa (A–Z)",
            "pw.special": "Ít nhất 1 ký tự đặc biệt (!@#$%…)",
            "pw.letters": "Cả chữ hoa và chữ thường",
            "pw.needUpper": "Thêm một chữ hoa (A–Z)",
            "pw.needLower": "Thêm một chữ thường (a–z)",
            "pw.numSym": "Một chữ số và một ký tự đặc biệt",
            "pw.needDigit": "Thêm một chữ số (0–9)",
            "pw.needSymbol": "Thêm một ký tự đặc biệt (!@#$…)",
            "pw.match": "Hai mật khẩu khớp nhau",
            "pw.allMet": "Mật khẩu đạt yêu cầu",
            "pw.met": "đã đạt",
            "pw.unmet": "chưa đạt",

            // Server error codes
            "error.INVALID_CREDENTIALS": "Email hoặc mật khẩu không chính xác.",
            "error.LOGIN_RATE_LIMITED": "Quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau 15 phút.",
            "error.RATE_LIMITED": "Bạn đã thử quá nhiều lần. Vui lòng thử lại sau.",
            "error.INVALID_EMAIL": "Vui lòng nhập địa chỉ email hợp lệ.",
            "error.INVALID_NAME": "Họ và tên cần có ít nhất 2 ký tự.",
            "error.INVALID_PHONE": "Số điện thoại chỉ gồm chữ số và các ký tự + ( ) - .",
            "error.PASSWORD_POLICY": "Mật khẩu chưa đáp ứng đủ yêu cầu bảo mật.",
            "error.PASSWORD_MISMATCH": "Mật khẩu nhập lại không khớp.",
            "error.PASSWORD_UNCHANGED": "Mật khẩu mới phải khác mật khẩu hiện tại.",
            "error.WRONG_CURRENT_PASSWORD": "Mật khẩu hiện tại không đúng.",
            "error.REGISTRATION_FAILED": "Không thể tạo tài khoản với thông tin này.",
            "error.RESET_TOKEN_INVALID": "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn. Hãy yêu cầu liên kết mới.",
            "error.UNAUTHENTICATED": "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.",
            "error.CSRF_TOKEN_REJECTED": "Phiên bảo mật đã hết hạn. Hãy tải lại trang và thử lại.",
            "error.CSRF_SESSION_REJECTED": "Phiên bảo mật không hợp lệ. Hãy đăng nhập lại.",
            "error.VALIDATION_ERROR": "Dữ liệu chưa hợp lệ. Hãy kiểm tra lại các trường.",
            "error.generic": "Không thể hoàn tất yêu cầu. Vui lòng thử lại.",

            // Dashboard shell
            "shell.workspace": "Không gian học tập",
            "shell.sampleData": "Dữ Liệu Mẫu",
            "shell.logout": "Đăng xuất",
            "shell.accountLabel": "Tài khoản đang đăng nhập",
            "shell.roleStudent": "Học viên",
            "shell.roleAdmin": "Quản trị viên",
            "shell.brandTagline": "Hiểu đúng năng lực · Vững bước tương lai",
            "shell.navLabel": "Điều hướng chính",
            "shell.navDashboard": "Tổng quan",
            "shell.navAssessment": "Làm bài kiểm tra",
            "shell.sectionJourney": "HÀNH TRÌNH",
            "shell.navSkills": "Báo cáo kỹ năng",
            "shell.navEvaluation": "Đánh giá AI",
            "shell.navProgress": "Theo dõi tiến độ",
            "shell.navRetest": "Kiểm tra lại",
            "shell.editGoal": "Sửa mục tiêu và quỹ thời gian",
            "shell.navTests": "Trung tâm kiểm tra",
            "shell.navRoadmap": "Lộ trình học tập",
            "shell.online": "Đã kết nối",
            "shell.onlineHint": "Kết nối máy chủ ổn định; tiến độ được lưu tự động.",
            "shell.offline": "Mất kết nối",
            "shell.offlineHint": "Không kết nối được máy chủ; thay đổi có thể chưa được lưu.",
            "shell.navProfile": "Hồ sơ cá nhân",
            "shell.sectionWorkflow": "QUY TRÌNH & TIỆN ÍCH",
            "shell.stepProfile": "Hồ sơ & mục tiêu",
            "shell.stepDiagnosis": "Chẩn đoán AI",
            "shell.stepResults": "Kết quả đánh giá",
            "shell.stepGaps": "Khoảng cách kỹ năng",
            "shell.currentGoal": "MỤC TIÊU HIỆN TẠI",
            "shell.help": "Hướng dẫn sử dụng",
            "shell.helpToast": "Chọn một mục ở thanh bên để bắt đầu. Bạn có thể mở hồ sơ, đánh giá, roadmap và các công cụ quản trị từ đây.",
            "shell.footer": "Nền tảng Đánh giá & Phát triển Năng lực Data Analyst",

            // Profile
            "profile.title": "Hồ sơ cá nhân",
            "profile.subtitle": "Quản lý thông tin tài khoản, ngôn ngữ và bảo mật đăng nhập.",
            "profile.memberSince": "Thành viên từ",
            "profile.lastLogin": "Đăng nhập gần nhất",
            "profile.passwordChanged": "Đổi mật khẩu lần cuối",
            "profile.role": "Vai trò",
            "profile.personalTitle": "Thông tin cá nhân",
            "profile.fullName": "Họ và tên",
            "profile.email": "Email",
            "profile.emailHint": "Email dùng để đăng nhập và không thể thay đổi tại đây.",
            "profile.phone": "Số điện thoại",
            "profile.phonePlaceholder": "Không bắt buộc",
            "profile.save": "Lưu thay đổi",
            "profile.saved": "Đã lưu thông tin cá nhân.",
            "profile.prefsTitle": "Tùy chọn",
            "profile.language": "Ngôn ngữ giao diện",
            "profile.languageHint": "Áp dụng ngay và được lưu vào tài khoản.",
            "profile.languageNote": "Lưu ý: nội dung bài học, đề kiểm tra và một số màn hình quy trình hiện chỉ có tiếng Việt.",
            "profile.languageSaved": "Đã đổi ngôn ngữ giao diện.",
            "profile.securityTitle": "Đổi mật khẩu",
            "profile.securityHint": "Sau khi đổi, mọi phiên đăng nhập khác của bạn sẽ bị đăng xuất.",
            "profile.currentPassword": "Mật khẩu hiện tại",
            "profile.newPassword": "Mật khẩu mới",
            "profile.confirmPassword": "Nhập lại mật khẩu mới",
            "profile.changePassword": "Cập nhật mật khẩu",
            "profile.passwordChangedToast": "Đã đổi mật khẩu. Các phiên đăng nhập khác đã được đăng xuất.",
            "profile.never": "Chưa có"
        },
        en: {
            "lang.label": "Language",
            "lang.vi": "Tiếng Việt",
            "lang.en": "English",
            "theme.toggle": "Switch between light, dark and system theme",
            "theme.label": "Theme",
            "theme.light": "Light",
            "theme.dark": "Dark",
            "theme.system": "Match system",

            "login.pageTitle": "Sign in · CareerAdapt AI",
            "login.brandTagline": "Know your true skills · Step firmly into the future",
            "login.eyebrow": "YOUR PERSONAL LEARNING SPACE",
            "login.heroLine1": "Clear progress.",
            "login.heroLine2": "Wider opportunities.",
            "login.heroBody": "Assess your skills with real work, understand your skill gaps and follow your own Data Analyst roadmap.",
            "login.proof1Title": "Evidence-based learning",
            "login.proof1Body": "Skills confirmed through assessments",
            "login.proof2Title": "Goal-driven roadmap",
            "login.proof2Body": "Track progress week by week",
            "login.proof3Title": "Your data, your control",
            "login.proof3Body": "Download or delete your profile at any time",
            "login.capsLock": "Caps Lock is on",
            "login.bot.hello": "Hi! I'm the CareerAdapt AI assistant. Sign in and let's keep going.",
            "login.bot.register": "Create an account and I'll help you measure your skills and plan your roadmap.",
            "login.bot.forgot": "No worries! Enter your registered email to get a reset link.",
            "login.bot.reset": "Pick a strong new password.",
            "login.bot.email": "Enter the email you signed up with.",
            "login.bot.emailNew": "Use an email you check, so you can recover your password if needed.",
            "login.bot.emailForgot": "A reset link goes to this email if it is registered.",
            "login.bot.name": "This name appears on your profile.",
            "login.bot.password": "My eyes are closed. Type your password in peace.",
            "login.bot.peek": "Your password is visible. Mind who's around.",
            "login.bot.caps": "Caps Lock is on. Check your capitals.",
            "login.bot.checking": "Give me a moment to check…",
            "login.bot.error": "Something isn't right. Check the message below and try again.",
            "login.bot.success": "Great! See the message below for the next step.",
            "login.footerSlogan": "Learn what matters, go further.",
            "landing.signIn": "Sign in",
            "landing.eyebrow": "FOR STUDENTS AIMING AT DATA ANALYST ROLES",
            "landing.title": "Know exactly how far you are from the job description.",
            "landing.lead": "CareerAdapt AI measures your ability with real tasks, compares it with the job description you choose, and builds a weekly study roadmap to close the gap.",
            "landing.start": "Start measuring your skills",
            "landing.how": "See how it works",
            "landing.point1": "Scores come from server-side test cases and rubrics",
            "landing.point2": "AI only comments; it never creates a score",
            "landing.point3": "Self-reported levels never count as ability",
            "landing.howTitle": "Five steps, one process",
            "landing.step1Title": "Report your skills",
            "landing.step1Body": "You state your current level to compare it with your results; the difficulty follows the level the job description requires.",
            "landing.step2Title": "Choose a target job description",
            "landing.step2Body": "Use a sourced job description from the library, or paste the one you want to apply for.",
            "landing.step3Title": "Take the test",
            "landing.step3Body": "SQL, Python, data quality, visualisation and report writing on sample data.",
            "landing.step4Title": "See the gap",
            "landing.step4Body": "For each skill: the verified level, the level the job requires, and why.",
            "landing.step5Title": "Follow the roadmap",
            "landing.step5Body": "A weekly roadmap with reviewed learning resources and follow-up checks.",
            "landing.getTitle": "What you get",
            "landing.card1Title": "A level backed by evidence",
            "landing.card1Body": "Four levels from Not started to Entry-level ready. A level is recorded only when a task proves it.",
            "landing.card2Title": "How competitive you are",
            "landing.card2Body": "See where you stand among people who took the same test. The leaderboard is anonymous; you choose whether to show your name.",
            "landing.card3Title": "Sourced salary reference",
            "landing.card3Body": "Median salary by years of experience from a public market report, with the source link and the date it was checked.",
            "landing.card4Title": "The source behind every result",
            "landing.card4Body": "The skill framework, job requirements, grading method and learning resources all state where they come from.",
            "landing.closeTitle": "Ready to find out where you stand?",
            "landing.closeCta": "Create an account or sign in",
            "landing.note": "Results reflect only the tasks measured. They are not a professional certificate or a promise of employment.",
            "login.about": "About CareerAdapt AI",
            "login.panelLabel": "Sign in or create an account",
            "login.tabsLabel": "Account options",
            "login.tabLogin": "Sign in",
            "login.tabRegister": "Create account",
            "login.titleLogin": "Welcome back",
            "login.subtitleLogin": "Sign in to continue your learning roadmap.",
            "login.titleRegister": "Start your journey",
            "login.subtitleRegister": "Create a learner account to keep your own progress.",
            "login.titleForgot": "Forgot your password?",
            "login.subtitleForgot": "Enter your registered email and we will send you a reset link.",
            "login.titleReset": "Set a new password",
            "login.subtitleReset": "Choose a new password for your account.",
            "login.email": "Email",
            "login.emailPlaceholder": "you@example.com",
            "login.password": "Password",
            "login.passwordPlaceholder": "Enter your password",
            "login.forgotLink": "Forgot password?",
            "login.submitLogin": "Sign in",
            "login.fullName": "Full name",
            "login.fullNamePlaceholder": "Alex Nguyen",
            "login.createPassword": "Create password",
            "login.createPasswordPlaceholder": "Create a strong password",
            "login.confirmPassword": "Re-enter password",
            "login.confirmPasswordPlaceholder": "Re-enter your password",
            "login.submitRegister": "Create learner account",
            "login.submitForgot": "Send reset link",
            "login.newPassword": "New password",
            "login.submitReset": "Save new password",
            "login.backToLogin": "← Back to sign in",
            "login.securityNote": "Your session is protected. Passwords are never stored as plain text.",
            "login.adminHelp": "Need admin access? Contact your system administrator for an account.",
            "login.footer": "Personalised learning platform",
            "login.processing": "Working…",
            "login.show": "Show",
            "login.hide": "Hide",
            "login.showPassword": "Show password",
            "login.hidePassword": "Hide password",
            "login.registered": "Account created for {email}. Sign in with the email and password you just created.",
            "login.forgotSent": "If this email is registered, a password reset link (valid for 30 minutes) has been sent to the inbox.",
            "login.resetDone": "Your new password is set. Sign in again; previous sessions have been signed out.",
            "login.csrfInit": "Could not start a secure session. Please reload the page.",
            "login.network": "Could not reach the server.",
            "login.fixFields": "Please complete the highlighted fields.",

            "pw.title": "Still needed:",
            "pw.length": "At least 8 characters",
            "pw.upper": "At least 1 uppercase letter (A–Z)",
            "pw.special": "At least 1 special character (!@#$%…)",
            "pw.letters": "Both uppercase and lowercase letters",
            "pw.needUpper": "Add an uppercase letter (A–Z)",
            "pw.needLower": "Add a lowercase letter (a–z)",
            "pw.numSym": "A number and a special character",
            "pw.needDigit": "Add a number (0–9)",
            "pw.needSymbol": "Add a special character (!@#$…)",
            "pw.match": "Both passwords match",
            "pw.allMet": "Password meets all requirements",
            "pw.met": "met",
            "pw.unmet": "not met",

            "error.INVALID_CREDENTIALS": "Incorrect email or password.",
            "error.LOGIN_RATE_LIMITED": "Too many failed sign-in attempts. Please try again in 15 minutes.",
            "error.RATE_LIMITED": "Too many attempts. Please try again later.",
            "error.INVALID_EMAIL": "Please enter a valid email address.",
            "error.INVALID_NAME": "Full name must have at least 2 characters.",
            "error.INVALID_PHONE": "Phone numbers may contain only digits and + ( ) - .",
            "error.PASSWORD_POLICY": "The password does not meet all security requirements.",
            "error.PASSWORD_MISMATCH": "The passwords do not match.",
            "error.PASSWORD_UNCHANGED": "The new password must differ from the current one.",
            "error.WRONG_CURRENT_PASSWORD": "The current password is incorrect.",
            "error.REGISTRATION_FAILED": "An account could not be created with these details.",
            "error.RESET_TOKEN_INVALID": "This reset link is invalid or has expired. Please request a new one.",
            "error.UNAUTHENTICATED": "Your session has expired. Please sign in again.",
            "error.CSRF_TOKEN_REJECTED": "Your secure session expired. Reload the page and try again.",
            "error.CSRF_SESSION_REJECTED": "Your secure session is invalid. Please sign in again.",
            "error.VALIDATION_ERROR": "Some fields are invalid. Please check them.",
            "error.generic": "The request could not be completed. Please try again.",

            "shell.workspace": "Learning space",
            "shell.sampleData": "Sample data",
            "shell.logout": "Sign out",
            "shell.accountLabel": "Signed-in account",
            "shell.roleStudent": "Learner",
            "shell.roleAdmin": "Administrator",
            "shell.brandTagline": "Know your true skills · Step firmly into the future",
            "shell.navLabel": "Main navigation",
            "shell.navDashboard": "Overview",
            "shell.navAssessment": "Take assessment",
            "shell.sectionJourney": "JOURNEY",
            "shell.navSkills": "Skill report",
            "shell.navEvaluation": "AI evaluation",
            "shell.navProgress": "Track progress",
            "shell.navRetest": "Retest",
            "shell.editGoal": "Edit goal and weekly time",
            "shell.navTests": "Test Center",
            "shell.navRoadmap": "Learning roadmap",
            "shell.online": "Connected",
            "shell.onlineHint": "Connected to the server; your progress is saved automatically.",
            "shell.offline": "Offline",
            "shell.offlineHint": "The server cannot be reached; changes may not be saved.",
            "shell.navProfile": "Profile",
            "shell.sectionWorkflow": "WORKFLOW & TOOLS",
            "shell.stepProfile": "Goals & background",
            "shell.stepDiagnosis": "AI diagnosis",
            "shell.stepResults": "Assessment results",
            "shell.stepGaps": "Skill gaps",
            "shell.currentGoal": "CURRENT GOAL",
            "shell.help": "Help",
            "shell.helpToast": "Pick an item in the sidebar to begin. Your profile, assessments, roadmap and admin tools are all reachable from there.",
            "shell.footer": "Data Analyst Skills Assessment & Development Platform",

            "profile.title": "Profile",
            "profile.subtitle": "Manage your account details, language and sign-in security.",
            "profile.memberSince": "Member since",
            "profile.lastLogin": "Last sign-in",
            "profile.passwordChanged": "Password last changed",
            "profile.role": "Role",
            "profile.personalTitle": "Personal information",
            "profile.fullName": "Full name",
            "profile.email": "Email",
            "profile.emailHint": "Your sign-in email cannot be changed here.",
            "profile.phone": "Phone number",
            "profile.phonePlaceholder": "Optional",
            "profile.save": "Save changes",
            "profile.saved": "Personal information saved.",
            "profile.prefsTitle": "Preferences",
            "profile.language": "Interface language",
            "profile.languageHint": "Applies immediately and is saved to your account.",
            "profile.languageNote": "Note: learning content, test questions and some workflow screens are currently available in Vietnamese only.",
            "profile.languageSaved": "Interface language updated.",
            "profile.securityTitle": "Change password",
            "profile.securityHint": "After changing it, all your other sessions will be signed out.",
            "profile.currentPassword": "Current password",
            "profile.newPassword": "New password",
            "profile.confirmPassword": "Re-enter new password",
            "profile.changePassword": "Update password",
            "profile.passwordChangedToast": "Password changed. Your other sessions have been signed out.",
            "profile.never": "Never"
        }
    };

    // Breadcrumb labels set by the existing workflow code (Vietnamese) -> English.
    const LEGACY_LABELS = {
        "Tổng quan": "Overview", "Hồ sơ & mục tiêu": "Goals & background", "Chẩn đoán AI": "AI diagnosis",
        "Đánh giá đầu vào": "Entry assessment", "Kết quả đánh giá": "Assessment results",
        "Khoảng cách kỹ năng": "Skill gaps", "Lộ trình học tập": "Learning roadmap", "Lộ trình 3 tuần": "Learning roadmap",
        "Trung tâm kiểm tra": "Retest", "Kiểm tra lại": "Retest", "Báo cáo kỹ năng": "Skill report",
        "Theo dõi tiến độ": "Track progress", "Đánh giá AI": "AI evaluation", "Làm bài kiểm tra": "Take assessment", "Quản trị hệ thống": "System administration", "Hồ sơ cá nhân": "Profile"
    };

    function readStored() {
        try {
            const value = window.localStorage.getItem(STORAGE_KEY);
            return SUPPORTED.includes(value) ? value : null;
        } catch (e) {
            return null;
        }
    }

    let current = readStored() || "vi";
    const listeners = [];

    function t(key, vars) {
        const text = (MESSAGES[current] && MESSAGES[current][key]) ?? MESSAGES.vi[key] ?? key;
        return vars ? text.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match)) : text;
    }

    function apply(root) {
        const scope = root || document;
        scope.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
        scope.querySelectorAll("[data-i18n-placeholder]").forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
        scope.querySelectorAll("[data-i18n-aria-label]").forEach(el => { el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel)); });
        scope.querySelectorAll("[data-i18n-title]").forEach(el => { el.title = t(el.dataset.i18nTitle); });
        document.documentElement.lang = current;
        document.querySelectorAll("[data-lang-option]").forEach(button => {
            const active = button.dataset.langOption === current;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-pressed", String(active));
        });
    }

    function setLang(lang, options = {}) {
        if (!SUPPORTED.includes(lang)) return;
        current = lang;
        try { window.localStorage.setItem(STORAGE_KEY, lang); } catch (e) { /* private mode: keep in memory */ }
        apply();
        if (!options.silent) listeners.forEach(listener => listener(lang));
    }

    function translateLegacy(text) {
        return current === "en" && LEGACY_LABELS[text] ? LEGACY_LABELS[text] : text;
    }

    function errorMessage(data, fallbackKey = "error.generic") {
        const code = data?.error?.code;
        if (code && MESSAGES.vi[`error.${code}`]) return t(`error.${code}`);
        return current === "vi" && data?.error?.message ? data.error.message : t(fallbackKey);
    }

    // Language buttons anywhere on the page: <button data-lang-option="en">
    document.addEventListener("click", event => {
        const button = event.target.closest("[data-lang-option]");
        if (button) setLang(button.dataset.langOption);
    });

    window.i18n = {
        t, apply, setLang, translateLegacy, errorMessage,
        getLang: () => current,
        hasStoredChoice: () => readStored() !== null,
        onChange: listener => listeners.push(listener)
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => apply());
    } else {
        apply();
    }
})();
