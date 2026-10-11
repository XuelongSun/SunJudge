# API 路由索引（自动生成）

由 `backend/scripts/generate_api_reference.py` 静态读取路由生成。完整调用规则和示例见 [API.md](API.md)。

参数是代码中读取的字段，并不表示全部必填；辅助函数中的作业字段见主文档。响应字段包含成功与错误分支，类型见 `backend/app/models.py` 的序列化方法。

## auth

| 方法 | 路径 | 角色 | 请求字段 | JSON 顶层字段 | 实现 |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/auth/register` | 公开 | payload.invite_code; payload.password; payload.role; payload.student_id; payload.student_name; payload.username | message, user | [register](../backend/app/routes/auth.py#L86) |
| POST | `/api/auth/login` | 公开 | payload.password; payload.username | message, user | [login](../backend/app/routes/auth.py#L171) |
| POST | `/api/auth/logout` | 登录用户 | — | message | [logout](../backend/app/routes/auth.py#L208) |
| GET | `/api/auth/me` | 公开 | — | user | [me](../backend/app/routes/auth.py#L214) |

## admin

| 方法 | 路径 | 角色 | 请求字段 | JSON 顶层字段 | 实现 |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/admin/classes` | teacher | class_payload.alias; class_payload.invite_enabled; class_payload.name; course_payload.code; course_payload.name; course_payload.semester; payload.alias; payload.class; payload.course; payload.roster | class, message, roster_count | [create_class_with_roster](../backend/app/routes/admin.py#L49) |
| PATCH | `/api/admin/classes/<int:class_id>` | teacher | class_payload.invite_enabled; class_payload.name; course_payload.code; course_payload.name; course_payload.semester; payload.class; payload.course | class, message | [update_class](../backend/app/routes/admin.py#L129) |
| GET | `/api/admin/classes` | teacher, admin | — | classes | [list_classes](../backend/app/routes/admin.py#L176) |
| POST | `/api/admin/classes/import-excel` | teacher | request.files.file; request.form.class_id; request.form.mode; request.form.preview | class_id, course_id, imported_count, message, preserved_registered_count, removed_count, updated_count | [import_classes_from_excel](../backend/app/routes/admin.py#L184) |
| GET | `/api/admin/classes/<int:class_id>/roster` | teacher | — | class, message, roster | [list_roster](../backend/app/routes/admin.py#L291) |
| POST | `/api/admin/classes/<int:class_id>/roster/batch` | teacher | payload.action; payload.entry_ids; payload.source_class | affected_count, message | [batch_roster_entries](../backend/app/routes/admin.py#L302) |
| POST | `/api/admin/classes/<int:class_id>/roster` | teacher | payload.no; payload.source_class; payload.student_id; payload.student_name; payload.student_no; payload.student_number | entry, message | [create_roster_entry](../backend/app/routes/admin.py#L335) |
| PATCH | `/api/admin/roster/<int:entry_id>` | teacher | payload.no; payload.source_class; payload.student_id; payload.student_name; payload.student_no; payload.student_number | entry, message | [update_roster_entry](../backend/app/routes/admin.py#L372) |
| DELETE | `/api/admin/roster/<int:entry_id>` | teacher | — | message | [delete_roster_entry](../backend/app/routes/admin.py#L413) |
| GET | `/api/admin/teachers` | admin | request.args.status | teachers | [list_teachers](../backend/app/routes/admin.py#L430) |
| PATCH | `/api/admin/teachers/<int:teacher_id>/status` | admin | payload.status | message, teacher | [update_teacher_status](../backend/app/routes/admin.py#L441) |

## classes

| 方法 | 路径 | 角色 | 请求字段 | JSON 顶层字段 | 实现 |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/classes/public` | 公开 | — | classes | [list_public_classes](../backend/app/routes/classes.py#L15) |
| GET | `/api/classes/my` | 登录用户 | — | classes, message | [list_my_classes](../backend/app/routes/classes.py#L27) |

## assignments

| 方法 | 路径 | 角色 | 请求字段 | JSON 顶层字段 | 实现 |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/admin/classes/<int:class_id>/assignments` | teacher, admin | — | assignments, class, message | [list_managed_assignments](../backend/app/routes/assignments.py#L108) |
| POST | `/api/admin/classes/<int:class_id>/assignments` | teacher | — | assignment, message | [create_assignment](../backend/app/routes/assignments.py#L128) |
| POST | `/api/admin/assignments/<int:assignment_id>/copy` | teacher | payload.class_id; payload.code | 文件响应 | [copy_assignment](../backend/app/routes/assignments.py#L163) |
| PATCH | `/api/admin/assignments/<int:assignment_id>` | teacher | payload.reset_grades; payload.reset_grading | assignment, message, requires_reset_grading, rerun_count, reset_grading | [update_assignment](../backend/app/routes/assignments.py#L205) |
| POST | `/api/admin/assignments/<int:assignment_id>/publish` | teacher | — | assignment, message | [publish_assignment](../backend/app/routes/assignments.py#L268) |
| DELETE | `/api/admin/assignments/<int:assignment_id>` | teacher | — | class_id, cleanup, message | [delete_assignment](../backend/app/routes/assignments.py#L290) |
| GET | `/api/admin/assignments/<int:assignment_id>/submissions` | teacher, admin | — | analysis, assignment, message, submissions, test_submissions | [list_assignment_submissions](../backend/app/routes/assignments.py#L314) |
| GET | `/api/admin/assignments/<int:assignment_id>/grades` | teacher, admin | — | analysis, assignment, class, message, rows | [get_assignment_grades](../backend/app/routes/assignments.py#L371) |
| GET | `/api/admin/assignments/<int:assignment_id>/grades.csv` | teacher, admin | — | message | [export_assignment_grades_csv](../backend/app/routes/assignments.py#L389) |
| GET | `/api/admin/assignments/<int:assignment_id>/scoremanager-commands` | teacher, admin | request.args.command_type; request.args.field; request.args.group_same_score; request.args.type | assignment, export, invalid_students, message | [export_assignment_scoremanager_commands](../backend/app/routes/assignments.py#L405) |
| GET | `/api/admin/llm-config` | teacher | — | config | [get_llm_config](../backend/app/routes/assignments.py#L441) |
| PUT | `/api/admin/llm-config` | teacher | payload.api_key; payload.base_url; payload.enabled; payload.model; payload.provider | config, message | [save_llm_config](../backend/app/routes/assignments.py#L449) |
| GET | `/api/admin/submissions/<int:submission_id>/preview` | teacher, admin | — | content, message, previewable, submission | [preview_submission_file](../backend/app/routes/assignments.py#L496) |
| GET | `/api/admin/submissions/<int:submission_id>/download` | teacher, admin | — | message | [download_submission_file](../backend/app/routes/assignments.py#L520) |
| POST | `/api/admin/submissions/<int:submission_id>/rerun-grading` | teacher | — | assignment_grade, message, queue_status, submission | [rerun_submission_grading](../backend/app/routes/assignments.py#L533) |
| POST | `/api/admin/submissions/<int:submission_id>/return` | teacher | — | assignment, cleanup, message | [return_submission_for_resubmit](../backend/app/routes/assignments.py#L556) |
| PATCH | `/api/admin/submissions/<int:submission_id>/grade` | teacher | payload.feedback; payload.file_reviews; payload.final_score; payload.reason; payload.status; payload.teacher_comment | assignment_grade, grading_result, message, submission | [review_submission_grade](../backend/app/routes/assignments.py#L579) |
| GET | `/api/classes/<int:class_id>/assignments` | student | — | assignments, class, message | [list_student_assignments](../backend/app/routes/assignments.py#L644) |
| POST | `/api/assignments/<int:assignment_id>/read` | student | — | assignment, message, read | [mark_assignment_read](../backend/app/routes/assignments.py#L665) |
| POST | `/api/assignments/<int:assignment_id>/submissions` | student | request.files.file; request.form.item_key; request.form.submission_item_key | assignment_grade, details, message, submission | [submit_assignment](../backend/app/routes/assignments.py#L680) |
| POST | `/api/assignments/<int:assignment_id>/confirm-submission` | student | — | assignment, assignment_grade, details, message, missing_keys, queue_status | [confirm_assignment_submission](../backend/app/routes/assignments.py#L773) |

## markdown_documents

| 方法 | 路径 | 角色 | 请求字段 | JSON 顶层字段 | 实现 |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/teacher/images` | teacher, student | — | 文件响应 | [list_teacher_images](../backend/app/routes/markdown_documents.py#L34) |
| GET | `/api/student/images` | teacher, student | — | 文件响应 | [list_teacher_images](../backend/app/routes/markdown_documents.py#L34) |
| POST | `/api/teacher/images` | teacher, student | request.files.file | 文件响应 | [upload_teacher_image](../backend/app/routes/markdown_documents.py#L44) |
| POST | `/api/student/images` | teacher, student | request.files.file | 文件响应 | [upload_teacher_image](../backend/app/routes/markdown_documents.py#L44) |
| DELETE | `/api/teacher/images/<asset_id>` | teacher, student | — | 文件响应 | [delete_teacher_image](../backend/app/routes/markdown_documents.py#L69) |
| DELETE | `/api/student/images/<asset_id>` | teacher, student | — | 文件响应 | [delete_teacher_image](../backend/app/routes/markdown_documents.py#L69) |
| POST | `/api/markdown-documents` | 登录用户 | payload.assignment_id; payload.class_id; payload.item_key; payload.kind | 文件响应 | [open_document](../backend/app/routes/markdown_documents.py#L94) |
| GET | `/api/markdown-documents/<int:document_id>` | 登录用户 | — | 文件响应 | [get_document](../backend/app/routes/markdown_documents.py#L149) |
| PUT | `/api/markdown-documents/<int:document_id>` | 登录用户 | payload.content; payload.revision | 文件响应 | [save_document](../backend/app/routes/markdown_documents.py#L155) |
| POST | `/api/markdown-documents/<int:document_id>/images` | 登录用户 | request.files.file | 文件响应 | [upload_image](../backend/app/routes/markdown_documents.py#L183) |
| GET | `/api/assets/<string:asset_id>/content` | 登录用户 | — | 文件响应 | [read_image](../backend/app/routes/markdown_documents.py#L208) |

## 运维

`GET /api/health`：公开；返回 `200 {"status":"ok"}`，只检查 HTTP 进程存活，不检查数据库、Docker 或任务队列。

框架自动提供 OPTIONS/HEAD；它们不计入业务路由。
