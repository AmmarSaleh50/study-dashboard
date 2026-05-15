import { useRef, useState } from "react";
import {
  ChevronRight,
  File as FileIcon,
  FileText,
  Folder,
  FolderPlus,
  Image as ImageIcon,
  Loader2,
  MoreHorizontal,
  Pencil,
  Presentation,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import {
  useCourses,
  useCreateFolder,
  useDeleteEntry,
  useFileSearch,
  useFilesList,
  useMoveEntry,
  useSyncMoodle,
  useUploadFile,
  type FileEntry,
} from "@/lib/queries";
import { fmtDateShort } from "@/lib/time";
import { cn } from "@/lib/cn";
import {
  Dropdown,
  DropdownContent,
  DropdownItem,
  DropdownTrigger,
} from "@/components/ui/dropdown";
import { FileViewer } from "./file-viewer";

export function FileBrowser({
  rootPrefix = "",
  rootLabel,
}: {
  rootPrefix?: string;
  rootLabel?: string;
}) {
  const { t } = useTranslation();
  const effectiveRootLabel = rootLabel ?? t("files.title");
  const [prefix, setPrefix] = useState(rootPrefix);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadFile();
  const createFolder = useCreateFolder();
  const deleteEntry = useDeleteEntry();
  const moveEntry = useMoveEntry();
  const syncMoodle = useSyncMoodle();
  const [syncStage, setSyncStage] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const search = useFileSearch(searchQuery);

  const { data, isPending, error } = useFilesList(prefix);
  // Hide the .keep placeholder we drop into empty folders so they survive
  // the filesystem's flat-file model (no true directory entries until a file exists).
  const visible = (data ?? []).filter((e) => e.name !== ".keep");

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length === 0) return;
    for (const file of files) {
      const path = prefix ? `${prefix}/${file.name}` : file.name;
      try {
        await upload.mutateAsync({ file, path });
        toast.success(t("files.uploadedName", { name: file.name }));
      } catch (err) {
        toast.error(
          t("files.uploadFailed", { name: file.name, msg: (err as Error).message || "—" })
        );
      }
    }
  }

  async function onNewFolder() {
    const name = window.prompt(t("files.newFolderPrompt"));
    if (!name?.trim()) return;
    const path = prefix ? `${prefix}/${name.trim()}` : name.trim();
    try {
      await createFolder.mutateAsync({ path });
      toast.success(t("files.createdFolder", { name: name.trim() }));
    } catch (err) {
      toast.error(t("files.folderFailed", { msg: (err as Error).message || "—" }));
    }
  }

  async function onRename(entry: FileEntry) {
    const newName = window.prompt(t("files.renamePrompt", { name: entry.name }), entry.name);
    if (!newName?.trim() || newName.trim() === entry.name) return;
    const parent = entry.path.includes("/")
      ? entry.path.slice(0, entry.path.lastIndexOf("/"))
      : "";
    const to = parent ? `${parent}/${newName.trim()}` : newName.trim();
    try {
      await moveEntry.mutateAsync({ from: entry.path, to, kind: entry.type });
      toast.success(t("files.renamedTo", { name: newName.trim() }));
    } catch (err) {
      toast.error(t("files.renameFailed", { msg: (err as Error).message || "—" }));
    }
  }

  // Detect current course from prefix (top-level segment matches a course's folder_name)
  const coursesQuery = useCourses();
  const topSegment = (rootPrefix || prefix).split("/")[0];
  const currentCourse =
    coursesQuery.data?.find((c) => (c.folder_name || c.code) === topSegment)?.code || null;

  async function onSyncMoodle() {
    const fastPath = Boolean(currentCourse);
    setSyncStage(t("files.syncStageLogin"));
    // Per-course is ~2-3s; full sync is ~8s — adjust stage timing accordingly
    const t1 = setTimeout(() => setSyncStage(t("files.syncStageScrape")), fastPath ? 800 : 1500);
    const t2 = setTimeout(() => setSyncStage(t("files.syncStageWrite")), fastPath ? 2200 : 6000);
    try {
      const result = await syncMoodle.mutateAsync(currentCourse ?? undefined);
      if (result.written_count > 0) {
        toast.success(t("files.syncDoneNew", { count: result.written_count }));
      } else {
        toast.success(t("files.syncDoneNoNew"));
      }
    } catch (err) {
      toast.error(t("files.syncFailed", { msg: (err as Error).message || "—" }));
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      setSyncStage(null);
    }
  }

  async function onDelete(entry: FileEntry) {
    const promptKey = entry.type === "folder" ? "files.deletePromptFolder" : "files.deletePromptFile";
    if (!window.confirm(t(promptKey, { name: entry.name }))) return;
    try {
      await deleteEntry.mutateAsync({ path: entry.path, kind: entry.type });
      toast.success(t("files.deletedName", { name: entry.name }));
    } catch (err) {
      toast.error(t("files.deleteFailed", { msg: (err as Error).message || "—" }));
    }
  }

  const relative = rootPrefix
    ? prefix.startsWith(rootPrefix)
      ? prefix.slice(rootPrefix.length).replace(/^\//, "")
      : prefix
    : prefix;
  const segments = relative ? relative.split("/").filter(Boolean) : [];

  function goTo(segmentIdx: number) {
    if (segmentIdx === -1) {
      setPrefix(rootPrefix);
      return;
    }
    const combined = segments.slice(0, segmentIdx + 1).join("/");
    setPrefix(rootPrefix ? `${rootPrefix}/${combined}` : combined);
  }

  const trimmedQuery = searchQuery.trim();
  const inSearchMode = trimmedQuery.length >= 2;

  return (
    <div className="flex flex-col gap-3">
      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t("files.searchPlaceholder")}
          className="w-full pl-9 pr-9 py-2 rounded-md border border-border/60 bg-surface-2 text-sm placeholder:text-subtle focus:outline-none focus:ring-2 focus:ring-info/50"
        />
        {searchQuery && (
          <button
            type="button"
            onClick={() => setSearchQuery("")}
            aria-label={t("common.clear", "Clear")}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted hover:text-fg"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Breadcrumbs + upload */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1 text-sm flex-wrap">
          <button
            type="button"
            onClick={() => goTo(-1)}
            className={cn(
              "px-1.5 py-0.5 rounded hover:bg-surface-2 transition-colors",
              segments.length === 0 ? "text-fg font-medium" : "text-muted hover:text-fg"
            )}
          >
            {effectiveRootLabel}
          </button>
          {segments.map((s, i) => (
            <div key={i} className="flex items-center gap-1">
              <ChevronRight className="h-3.5 w-3.5 text-subtle" />
              <button
                type="button"
                onClick={() => goTo(i)}
                className={cn(
                  "px-1.5 py-0.5 rounded hover:bg-surface-2 transition-colors",
                  i === segments.length - 1 ? "text-fg font-medium" : "text-muted hover:text-fg"
                )}
              >
                {s}
              </button>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onSyncMoodle}
            disabled={syncMoodle.isPending}
            className="touch-target inline-flex items-center gap-2 rounded-md border border-border/60 bg-surface-2 hover:bg-surface-2/80 px-3 text-sm font-medium disabled:opacity-60 transition-colors min-w-[10rem] justify-center"
          >
            {syncMoodle.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin shrink-0" />
            ) : (
              <RefreshCw className="h-4 w-4 shrink-0" />
            )}
            <span className="truncate">{syncStage ?? (currentCourse ? t("files.syncMoodleCourse", { code: currentCourse }) : t("files.syncMoodle"))}</span>
          </button>
          <button
            type="button"
            onClick={onNewFolder}
            disabled={createFolder.isPending}
            className="touch-target inline-flex items-center gap-2 rounded-md border border-border/60 bg-surface-2 hover:bg-surface-2/80 px-3 text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {createFolder.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FolderPlus className="h-4 w-4" />
            )}
            {t("files.newFolder")}
          </button>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={upload.isPending}
            className="touch-target inline-flex items-center gap-2 rounded-md border border-border/60 bg-surface-2 hover:bg-surface-2/80 px-3 text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {upload.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            {t("files.upload")}
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={onUpload}
          className="hidden"
        />
      </div>

      {/* Entries (or search results) */}
      <div className="card overflow-hidden">
        {inSearchMode ? (
          search.isPending ? (
            <div className="py-12 flex justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted" />
            </div>
          ) : search.error ? (
            <p className="p-4 text-sm text-critical">{t("files.searchFailed")}</p>
          ) : !search.data || search.data.length === 0 ? (
            <p className="p-6 text-sm text-muted text-center">
              {t("files.searchEmpty", { q: trimmedQuery })}
            </p>
          ) : (
            <ul className="divide-y divide-border/50">
              {search.data.map((hit) => (
                <li key={hit.path} className="relative">
                  <button
                    type="button"
                    onClick={() => setOpenPath(hit.path)}
                    className="w-full text-left flex items-start gap-3 px-4 py-3 hover:bg-surface-2 transition-colors"
                  >
                    <FileText className="h-4 w-4 text-critical flex-shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{hit.path}</p>
                      <p
                        className="text-xs text-muted mt-1 line-clamp-2"
                        dangerouslySetInnerHTML={{ __html: renderSnippet(hit.snippet) }}
                      />
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )
        ) : isPending ? (
          <div className="py-12 flex justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted" />
          </div>
        ) : error ? (
          <p className="p-4 text-sm text-critical">{t("files.couldNotLoad")}</p>
        ) : visible.length === 0 ? (
          <p className="p-6 text-sm text-muted text-center">{t("files.emptyFolder")}</p>
        ) : (
          <ul className="divide-y divide-border/50">
            {visible.map((e) => (
              <li key={e.path} className="relative flex items-center group">
                <button
                  type="button"
                  onClick={() => (e.type === "folder" ? setPrefix(e.path) : setOpenPath(e.path))}
                  className="flex-1 min-w-0 text-left flex items-center gap-3 px-4 py-3 hover:bg-surface-2 transition-colors touch-target"
                >
                  <EntryIcon entry={e} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{e.name}</p>
                    {e.type === "file" && (
                      <p className="text-xs text-muted mt-0.5">
                        {e.size ? fmtBytes(e.size) : "—"}
                        {e.updated_at && ` · ${fmtDateShort(e.updated_at)}`}
                      </p>
                    )}
                  </div>
                  {e.type === "folder" && <ChevronRight className="h-4 w-4 text-subtle" />}
                </button>
                <Dropdown>
                  <DropdownTrigger asChild>
                    <button
                      type="button"
                      aria-label={t("files.actionsFor", { name: e.name })}
                      className="touch-target shrink-0 px-3 py-3 text-muted hover:text-fg hover:bg-surface-2 transition-colors"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>
                  </DropdownTrigger>
                  <DropdownContent align="end">
                    <DropdownItem onSelect={() => onRename(e)}>
                      <Pencil className="h-4 w-4" /> {t("files.renameAction")}
                    </DropdownItem>
                    <DropdownItem danger onSelect={() => onDelete(e)}>
                      <Trash2 className="h-4 w-4" /> {t("files.deleteAction")}
                    </DropdownItem>
                  </DropdownContent>
                </Dropdown>
              </li>
            ))}
          </ul>
        )}
      </div>

      {openPath && <FileViewer path={openPath} onClose={() => setOpenPath(null)} />}
    </div>
  );
}

function EntryIcon({ entry }: { entry: FileEntry }) {
  if (entry.type === "folder")
    return <Folder className="h-4 w-4 text-info flex-shrink-0" />;
  const ext = entry.name.toLowerCase().split(".").pop() || "";
  if (ext === "pdf")
    return <FileText className="h-4 w-4 text-critical flex-shrink-0" />;
  if (["png", "jpg", "jpeg", "webp", "gif"].includes(ext))
    return <ImageIcon className="h-4 w-4 text-info flex-shrink-0" />;
  if (["md", "txt", "typ"].includes(ext))
    return <FileText className="h-4 w-4 text-muted flex-shrink-0" />;
  if (["pptx", "ppt", "key"].includes(ext))
    return <Presentation className="h-4 w-4 text-warn flex-shrink-0" />;
  return <FileIcon className="h-4 w-4 text-muted flex-shrink-0" />;
}

// Snippet comes from Postgres ts_headline with <<term>> markers around hits.
// Escape to keep dangerouslySetInnerHTML safe, then convert markers to <mark>.
function renderSnippet(raw: string): string {
  if (!raw) return "";
  const escaped = raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped
    .replace(/&lt;&lt;/g, '<mark class="bg-info/20 text-info rounded px-0.5">')
    .replace(/&gt;&gt;/g, "</mark>");
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
