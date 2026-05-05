# ERP Documents Module

The Documents module allows ERP users to browse, download, upload, and trash-manage files stored on the Windows server's local disk, linked to each Product.

---

## 1. Configuration

Add the following environment variables (or set them in `config/settings.py`):

| Variable | Default | Description |
|---|---|---|
| `ERP_DOCS_ROOT` | `C:\ERP_VAULT\docs` | Root directory where product document folders are stored |
| `ERP_TRASH_ROOT` | `C:\ERP_VAULT\trash` | Recycle bin directory (deleted items moved here) |
| `ERP_TMP_ROOT` | `C:\ERP_VAULT\tmp` | Temporary directory for atomic uploads |
| `ERP_TRASH_RETENTION_DAYS` | `30` | Days before trash items are permanently deleted |
| `ERP_DOCS_ADMIN_GROUP` | `docs_admin` | Django Group name with full documents admin rights |

### Example `.env` (Windows)
```
ERP_DOCS_ROOT=C:\ERP_VAULT\docs
ERP_TRASH_ROOT=C:\ERP_VAULT\trash
ERP_TMP_ROOT=C:\ERP_VAULT\tmp
ERP_TRASH_RETENTION_DAYS=30
ERP_DOCS_ADMIN_GROUP=docs_admin
```

---

## 2. Initial Setup

### 2.1 Copy your existing folder structure
```
robocopy Z:\Documents C:\ERP_VAULT\docs /MIR /R:2 /W:5 /XA:H /LOG:C:\ERP_VAULT\copy.log
```

### 2.2 NTFS permissions (recommended)
Restrict `C:\ERP_VAULT\` to the `erp_service` account and Administrators only:
```powershell
icacls "C:\ERP_VAULT" /inheritance:r /grant "erp_service:(OI)(CI)F" /grant "Administrators:(OI)(CI)F"
```

### 2.3 Apply Django migrations
```
python manage.py migrate
```

### 2.4 Create the `docs_admin` group
In Django Admin → Groups → Add group: name it `docs_admin`.
Then assign the group to privileged users (managers).

---

## 3. Permissions Model

| Role | Browse + Download | Upload | Delete → Trash | Restore | Set Folder |
|---|---|---|---|---|---|
| Authenticated user | ✅ | ❌ | ❌ | ❌ | ❌ |
| `docs_admin` group | ✅ | ✅ | ✅ | ✅ | ✅ |
| Django superuser | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 4. Using the Folder Picker

1. Open a Product's detail page.
2. Click **📁 Vybrať priečinok** (visible only to `docs_admin` users).
3. A modal opens showing the folder tree rooted at `ERP_DOCS_ROOT`.
4. Click the **▶** arrow to expand sub-folders (lazy loading — no full tree load).
5. Click a folder name to select it (highlighted in blue).
6. Click **✅ Použiť tento priečinok** to save.

The relative path (e.g., `AA Hengstler 2026/Database/006 - 3532011922`) is stored in `Product.documents_path` and displayed on the product page.

---

## 5. Browsing and Downloading

Once a product has a `documents_path` set:

- The product detail page shows a **Documents** section with folder/file listing.
- Click a folder 📁 to navigate into it (breadcrumb navigation).
- Click **⬇️** next to a file to download it via the ERP (authenticated, streamed, no direct file system access from browser).
- Click **🔄** to refresh the listing.

---

## 6. Uploading Files

`docs_admin` users see an **⬆️ Nahrať** button.  
Multi-file upload is supported.

**Rules:**
- Uploads go to the currently viewed subfolder.
- Files are written atomically (tmp → move).
- Filename collisions are resolved automatically (`file (2).pdf`, `file (3).pdf`, …).
- Blocked extensions: `.exe .bat .cmd .ps1 .sh .vbs .js .jar .msi .dll .scr .com .pif .hta .wsf`

---

## 7. Delete → Trash

`docs_admin` users see a **🗑️** button next to each file and folder.

- Clicking it moves the item to `ERP_TRASH_ROOT/<timestamp>__<user>/<original_relative_path>`.
- The original path is preserved in the trash prefix for easy auditing.
- Every delete is logged in `DocumentAuditLog`.

### Viewing and restoring from trash

1. Click **🗑️ Zobraziť kôš produktu** (below the Documents section).
2. A panel appears showing deleted items for this product (up to 200 recent).
3. Click **↩️ Obnoviť** to restore a file to its original location.
   - If a file already exists at the destination, the restored file gets a `(2)` suffix.

---

## 8. Automatic Trash Cleanup

Run the management command (e.g., via Windows Task Scheduler):

```
python manage.py cleanup_trash
```

Options:
```
python manage.py cleanup_trash --dry-run        # preview without deleting
python manage.py cleanup_trash --days 7         # override retention to 7 days
```

### Scheduling on Windows (Task Scheduler)
1. Open Task Scheduler → Create Basic Task.
2. Trigger: Daily, 02:00.
3. Action: Start a program  
   Program: `C:\Python312\python.exe`  
   Arguments: `manage.py cleanup_trash`  
   Start in: `C:\path\to\erp_system`

---

## 9. API Endpoints

| Method | URL | Auth required | Description |
|---|---|---|---|
| GET | `/api/docs/tree/?path=<rel>` | Login | Lazy folder tree for picker |
| POST | `/api/docs/<pk>/set-path/` | `docs_admin` | Set product.documents_path |
| GET | `/api/docs/<pk>/list/?subpath=<rel>` | Login | List folder contents |
| GET | `/api/docs/<pk>/download/?subpath=<rel>` | Login | Stream file download |
| POST | `/api/docs/<pk>/upload/?subpath=<rel>` | `docs_admin` | Upload files (multipart) |
| POST | `/api/docs/<pk>/delete/` | `docs_admin` | Move to trash (JSON body: `{subpath}`) |
| GET | `/api/docs/trash/?produkt_pk=<id>` | Login | List trash entries |
| POST | `/api/docs/trash/restore/` | `docs_admin` | Restore from trash (JSON body: `{log_id}`) |

All endpoints return `{"status": "ok"|"error", "message": "..."}`.

---

## 10. Audit Log

All document actions are recorded in the `DocumentAuditLog` model (visible in Django Admin):

| Action | When |
|---|---|
| `upload` | File uploaded successfully |
| `delete_to_trash` | File/folder moved to trash |
| `restore` | Item restored from trash |
| `cleanup` | Item permanently deleted by cleanup command |
| `set_path` | Product's `documents_path` changed |

Fields: user, timestamp, produkt, action, src_rel_path, dest_rel_path, file_size.

---

## 11. Path Safety

- All paths from requests are normalised (backslash → forward slash).
- Absolute paths (`/etc/passwd`, `C:\Windows`) are rejected with HTTP 400.
- `..` traversal is blocked: the resolved absolute path must start with `ERP_DOCS_ROOT`.
- `ERP_TRASH_ROOT` is completely separate from `ERP_DOCS_ROOT` to prevent mixing.

---

## 12. Backup Guidance

### Documents backup
```batch
robocopy C:\ERP_VAULT\docs E:\ERP_BACKUP\docs /MIR /R:2 /W:5 /FFT /Z /XA:H /XD "tmp" /LOG+:C:\ERP_VAULT\backups\robocopy_docs.log
```

### Trash backup (optional — already has 30-day retention)
```batch
robocopy C:\ERP_VAULT\trash E:\ERP_BACKUP\trash /MIR /R:2 /W:5 /LOG+:C:\ERP_VAULT\backups\robocopy_trash.log
```

### Database backup
```batch
python manage.py dumpdata > C:\ERP_VAULT\backups\db\%date:~6,4%-%date:~3,2%-%date:~0,2%.json
```

Rotate 2 external disks and keep one disconnected (ransomware protection).
