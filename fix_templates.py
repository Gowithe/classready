"""
fix_templates.py - Fix remaining url_for() endpoints in templates
Works by simple string replacement - no regex issues.
"""
import os, shutil

# Only endpoints that NEED to change (moved to blueprints but not yet prefixed)
# Endpoints staying in app.py (dashboard, topic_detail, view_slides, etc.) are NOT listed
FIXES = {
    # auth
    "url_for('landing'":                    "url_for('auth.landing'",
    'url_for("landing"':                    'url_for("auth.landing"',
    "url_for('register'":                   "url_for('auth.register'",
    'url_for("register"':                   'url_for("auth.register"',
    "url_for('verify_email'":               "url_for('auth.verify_email'",
    'url_for("verify_email"':               'url_for("auth.verify_email"',
    "url_for('login'":                      "url_for('auth.login'",
    'url_for("login"':                      'url_for("auth.login"',
    "url_for('logout'":                     "url_for('auth.logout'",
    'url_for("logout"':                     'url_for("auth.logout"',
    "url_for('resend_verification'":        "url_for('auth.resend_verification'",
    'url_for("resend_verification"':        'url_for("auth.resend_verification"',
    "url_for('forgot_password'":            "url_for('auth.forgot_password'",
    'url_for("forgot_password"':            'url_for("auth.forgot_password"',
    "url_for('reset_password'":             "url_for('auth.reset_password'",
    'url_for("reset_password"':             'url_for("auth.reset_password"',
    "url_for('my_account'":                 "url_for('auth.my_account'",
    'url_for("my_account"':                 'url_for("auth.my_account"',
    "url_for('my_account_update'":          "url_for('auth.my_account_update'",
    'url_for("my_account_update"':          'url_for("auth.my_account_update"',
    "url_for('my_account_change_password'": "url_for('auth.my_account_change_password'",
    'url_for("my_account_change_password"': 'url_for("auth.my_account_change_password"',

    # classroom
    "url_for('classrooms'":                    "url_for('classroom.classrooms'",
    'url_for("classrooms"':                    'url_for("classroom.classrooms"',
    "url_for('classroom_create'":              "url_for('classroom.classroom_create'",
    'url_for("classroom_create"':              'url_for("classroom.classroom_create"',
    "url_for('classroom_detail'":              "url_for('classroom.classroom_detail'",
    'url_for("classroom_detail"':              'url_for("classroom.classroom_detail"',
    "url_for('classroom_edit'":                "url_for('classroom.classroom_edit'",
    'url_for("classroom_edit"':                'url_for("classroom.classroom_edit"',
    "url_for('classroom_delete'":              "url_for('classroom.classroom_delete'",
    'url_for("classroom_delete"':              'url_for("classroom.classroom_delete"',
    "url_for('classroom_add_student'":         "url_for('classroom.classroom_add_student'",
    'url_for("classroom_add_student"':         'url_for("classroom.classroom_add_student"',
    "url_for('classroom_import_students'":     "url_for('classroom.classroom_import_students'",
    'url_for("classroom_import_students"':     'url_for("classroom.classroom_import_students"',
    "url_for('classroom_student_edit'":        "url_for('classroom.classroom_student_edit'",
    'url_for("classroom_student_edit"':        'url_for("classroom.classroom_student_edit"',
    "url_for('classroom_student_delete'":      "url_for('classroom.classroom_student_delete'",
    'url_for("classroom_student_delete"':      'url_for("classroom.classroom_student_delete"',
    "url_for('classroom_assign'":              "url_for('classroom.classroom_assign'",
    'url_for("classroom_assign"':              'url_for("classroom.classroom_assign"',
    "url_for('assignment_detail'":             "url_for('classroom.assignment_detail'",
    'url_for("assignment_detail"':             'url_for("classroom.assignment_detail"',
    "url_for('api_get_classrooms'":            "url_for('classroom.api_get_classrooms'",
    'url_for("api_get_classrooms"':            'url_for("classroom.api_get_classrooms"',
    "url_for('api_get_classroom_students'":    "url_for('classroom.api_get_classroom_students'",
    'url_for("api_get_classroom_students"':    'url_for("classroom.api_get_classroom_students"',
    "url_for('api_public_classroom_students'": "url_for('classroom.api_public_classroom_students'",
    'url_for("api_public_classroom_students"': 'url_for("classroom.api_public_classroom_students"',

    # game
    "url_for('game'":                        "url_for('game.game'",
    'url_for("game"':                        'url_for("game.game"',
    "url_for('api_game_sets'":               "url_for('game.api_game_sets'",
    'url_for("api_game_sets"':               'url_for("game.api_game_sets"',
    "url_for('api_game_sessions'":           "url_for('game.api_game_sessions'",
    'url_for("api_game_sessions"':           'url_for("game.api_game_sessions"',
    "url_for('api_game_session_get'":        "url_for('game.api_game_session_get'",
    'url_for("api_game_session_get"':        'url_for("game.api_game_session_get"',
    "url_for('api_game_session_save'":       "url_for('game.api_game_session_save'",
    'url_for("api_game_session_save"':       'url_for("game.api_game_session_save"',
    "url_for('game_memory'":                 "url_for('game.game_memory'",
    'url_for("game_memory"':                 'url_for("game.game_memory"',
    "url_for('game_millionaire'":            "url_for('game.game_millionaire'",
    'url_for("game_millionaire"':            'url_for("game.game_millionaire"',
    "url_for('api_sentence_builder_custom'": "url_for('game.api_sentence_builder_custom'",
    'url_for("api_sentence_builder_custom"': 'url_for("game.api_sentence_builder_custom"',
    "url_for('game_sentence_builder'":       "url_for('game.game_sentence_builder'",
    'url_for("game_sentence_builder"':       'url_for("game.game_sentence_builder"',

    # practice
    "url_for('practice'":                      "url_for('practice.practice'",
    'url_for("practice"':                      'url_for("practice.practice"',
    "url_for('api_practice_submit'":           "url_for('practice.api_practice_submit'",
    'url_for("api_practice_submit"':           'url_for("practice.api_practice_submit"',
    "url_for('api_practice_create_link'":      "url_for('practice.api_practice_create_link'",
    'url_for("api_practice_create_link"':      'url_for("practice.api_practice_create_link"',
    "url_for('practice_pdf'":                  "url_for('practice.practice_pdf'",
    'url_for("practice_pdf"':                  'url_for("practice.practice_pdf"',
    "url_for('practice_scores'":               "url_for('practice.practice_scores'",
    'url_for("practice_scores"':               'url_for("practice.practice_scores"',
    "url_for('practice_scores_csv'":           "url_for('practice.practice_scores_csv'",
    'url_for("practice_scores_csv"':           'url_for("practice.practice_scores_csv"',
    "url_for('practice_scores_excel'":         "url_for('practice.practice_scores_excel'",
    'url_for("practice_scores_excel"':         'url_for("practice.practice_scores_excel"',
    "url_for('public_practice'":               "url_for('practice.public_practice'",
    'url_for("public_practice"':               'url_for("practice.public_practice"',
    "url_for('api_public_practice_submit'":    "url_for('practice.api_public_practice_submit'",
    'url_for("api_public_practice_submit"':    'url_for("practice.api_public_practice_submit"',
    "url_for('practice_fill_blanks'":          "url_for('practice.practice_fill_blanks'",
    'url_for("practice_fill_blanks"':          'url_for("practice.practice_fill_blanks"',
    "url_for('api_fill_blanks_create_link'":   "url_for('practice.api_fill_blanks_create_link'",
    'url_for("api_fill_blanks_create_link"':   'url_for("practice.api_fill_blanks_create_link"',
    "url_for('practice_fill_blanks_scores'":   "url_for('practice.practice_fill_blanks_scores'",
    'url_for("practice_fill_blanks_scores"':   'url_for("practice.practice_fill_blanks_scores"',
    "url_for('public_fill_blanks'":            "url_for('practice.public_fill_blanks'",
    'url_for("public_fill_blanks"':            'url_for("practice.public_fill_blanks"',
    "url_for('api_public_fill_blanks_submit'": "url_for('practice.api_public_fill_blanks_submit'",
    'url_for("api_public_fill_blanks_submit"': 'url_for("practice.api_public_fill_blanks_submit"',
    "url_for('practice_unscramble'":           "url_for('practice.practice_unscramble'",
    'url_for("practice_unscramble"':           'url_for("practice.practice_unscramble"',
    "url_for('api_unscramble_create_link'":    "url_for('practice.api_unscramble_create_link'",
    'url_for("api_unscramble_create_link"':    'url_for("practice.api_unscramble_create_link"',
    "url_for('practice_unscramble_scores'":    "url_for('practice.practice_unscramble_scores'",
    'url_for("practice_unscramble_scores"':    'url_for("practice.practice_unscramble_scores"',
    "url_for('public_unscramble'":             "url_for('practice.public_unscramble'",
    'url_for("public_unscramble"':             'url_for("practice.public_unscramble"',
    "url_for('api_public_unscramble_submit'":  "url_for('practice.api_public_unscramble_submit'",
    'url_for("api_public_unscramble_submit"':  'url_for("practice.api_public_unscramble_submit"',
    "url_for('qr_practice_mcq'":              "url_for('practice.qr_practice_mcq'",
    'url_for("qr_practice_mcq"':              'url_for("practice.qr_practice_mcq"',
    "url_for('qr_practice_fill'":             "url_for('practice.qr_practice_fill'",
    'url_for("qr_practice_fill"':             'url_for("practice.qr_practice_fill"',
    "url_for('qr_practice_unscramble'":       "url_for('practice.qr_practice_unscramble'",
    'url_for("qr_practice_unscramble"':       'url_for("practice.qr_practice_unscramble"',
    "url_for('api_create_study_link'":        "url_for('practice.api_create_study_link'",
    'url_for("api_create_study_link"':        'url_for("practice.api_create_study_link"',
    "url_for('api_study_submit'":             "url_for('practice.api_study_submit'",
    'url_for("api_study_submit"':             'url_for("practice.api_study_submit"',
    "url_for('public_self_study'":            "url_for('practice.public_self_study'",
    'url_for("public_self_study"':            'url_for("practice.public_self_study"',

    # library
    "url_for('library'":              "url_for('library.library'",
    'url_for("library"':              'url_for("library.library"',
    "url_for('library_subject'":      "url_for('library.library_subject'",
    'url_for("library_subject"':      'url_for("library.library_subject"',
    "url_for('library_unit_detail'":  "url_for('library.library_unit_detail'",
    'url_for("library_unit_detail"':  'url_for("library.library_unit_detail"',
    "url_for('library_clone_unit'":   "url_for('library.library_clone_unit'",
    'url_for("library_clone_unit"':   'url_for("library.library_clone_unit"',
    "url_for('library_rate_unit'":    "url_for('library.library_rate_unit'",
    'url_for("library_rate_unit"':    'url_for("library.library_rate_unit"',
    "url_for('library_search'":       "url_for('library.library_search'",
    'url_for("library_search"':       'url_for("library.library_search"',
    "url_for('premium_page'":         "url_for('library.premium_page'",
    'url_for("premium_page"':         'url_for("library.premium_page"',
    "url_for('premium_subscribe'":    "url_for('library.premium_subscribe'",
    'url_for("premium_subscribe"':    'url_for("library.premium_subscribe"',

    # payment
    "url_for('pricing'":          "url_for('payment.pricing'",
    'url_for("pricing"':          'url_for("payment.pricing"',
    "url_for('api_user_limits'":  "url_for('payment.api_user_limits'",
    'url_for("api_user_limits"':  'url_for("payment.api_user_limits"',
    "url_for('payment_create'":   "url_for('payment.payment_create'",
    'url_for("payment_create"':   'url_for("payment.payment_create"',
    "url_for('payment_page'":     "url_for('payment.payment_page'",
    'url_for("payment_page"':     'url_for("payment.payment_page"',
    "url_for('payment_verify'":   "url_for('payment.payment_verify'",
    'url_for("payment_verify"':   'url_for("payment.payment_verify"',

    # admin
    "url_for('admin_dashboard'":                "url_for('admin.admin_dashboard'",
    'url_for("admin_dashboard"':                'url_for("admin.admin_dashboard"',
    "url_for('admin_create_topic'":             "url_for('admin.admin_create_topic'",
    'url_for("admin_create_topic"':             'url_for("admin.admin_create_topic"',
    "url_for('admin_edit_topic'":               "url_for('admin.admin_edit_topic'",
    'url_for("admin_edit_topic"':               'url_for("admin.admin_edit_topic"',
    "url_for('admin_delete_topic'":             "url_for('admin.admin_delete_topic'",
    'url_for("admin_delete_topic"':             'url_for("admin.admin_delete_topic"',
    "url_for('admin_library'":                  "url_for('admin.admin_library'",
    'url_for("admin_library"':                  'url_for("admin.admin_library"',
    "url_for('admin_library_subject_create'":   "url_for('admin.admin_library_subject_create'",
    'url_for("admin_library_subject_create"':   'url_for("admin.admin_library_subject_create"',
    "url_for('admin_library_subject_edit'":     "url_for('admin.admin_library_subject_edit'",
    'url_for("admin_library_subject_edit"':     'url_for("admin.admin_library_subject_edit"',
    "url_for('admin_library_unit_create'":      "url_for('admin.admin_library_unit_create'",
    'url_for("admin_library_unit_create"':      'url_for("admin.admin_library_unit_create"',
    "url_for('admin_library_unit_edit'":        "url_for('admin.admin_library_unit_edit'",
    'url_for("admin_library_unit_edit"':        'url_for("admin.admin_library_unit_edit"',
    "url_for('admin_library_unit_delete'":      "url_for('admin.admin_library_unit_delete'",
    'url_for("admin_library_unit_delete"':      'url_for("admin.admin_library_unit_delete"',
    "url_for('admin_library_unit_generate'":    "url_for('admin.admin_library_unit_generate'",
    'url_for("admin_library_unit_generate"':    'url_for("admin.admin_library_unit_generate"',
    "url_for('admin_library_import_from_topic'":"url_for('admin.admin_library_import_from_topic'",
    'url_for("admin_library_import_from_topic"':'url_for("admin.admin_library_import_from_topic"',
    "url_for('admin_payments'":                 "url_for('admin.admin_payments'",
    'url_for("admin_payments"':                 'url_for("admin.admin_payments"',
    "url_for('admin_users'":                    "url_for('admin.admin_users'",
    'url_for("admin_users"':                    'url_for("admin.admin_users"',
    "url_for('admin_adjust_user_expiry'":       "url_for('admin.admin_adjust_user_expiry'",
    'url_for("admin_adjust_user_expiry"':       'url_for("admin.admin_adjust_user_expiry"',
}

# Safety: never double-prefix (e.g. don't turn game.game into game.game.game)
SAFE_FIXES = {}
for old, new in FIXES.items():
    # Skip if the "new" version already exists as a key (would mean double-prefixing)
    SAFE_FIXES[old] = new


def fix_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    count = 0

    for old, new in SAFE_FIXES.items():
        # Don't replace if already has blueprint prefix
        # e.g. skip "url_for('game'" if it's actually "url_for('game.game'"
        # We check by ensuring the old string is NOT immediately followed by a dot
        if old in content:
            # Make sure we're not matching an already-prefixed version
            # e.g. "url_for('game'" should match, but not if it's part of "url_for('game.game'"
            # The old key already ends before the quote closes, so check what follows
            pos = 0
            while True:
                idx = content.find(old, pos)
                if idx == -1:
                    break
                # Check character after the match
                after_idx = idx + len(old)
                if after_idx < len(content) and content[after_idx] == '.':
                    # Already prefixed, skip this occurrence
                    pos = after_idx
                    continue
                # Safe to replace this occurrence
                content = content[:idx] + new + content[after_idx:]
                count += 1
                pos = idx + len(new)

    if count > 0:
        # Backup
        shutil.copy2(filepath, filepath + ".bak")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return count


def main():
    template_dir = "templates"
    if not os.path.isdir(template_dir):
        print(f"ERROR: '{template_dir}' directory not found!")
        print(f"Current directory: {os.getcwd()}")
        return

    total = 0
    for fn in sorted(os.listdir(template_dir)):
        if not fn.endswith(".html"):
            continue
        fp = os.path.join(template_dir, fn)
        n = fix_file(fp)
        if n:
            print(f"  Fixed: {fp}  ({n} replacements)")
            total += n

    print(f"\nTotal: {total} url_for() calls fixed across all templates.")
    if total:
        print("Backups saved as *.bak files.")
    else:
        print("Nothing to fix - all endpoints already correct!")


if __name__ == "__main__":
    main()
