export interface DocumentListItem {
  id: number;
  external_id: number;
  section: string;
  url: string;
  title_ru: string | null;
  title_kk: string | null;
  status: string | null;
  doc_type: string | null;
  government_body: string | null;
  created_date: string | null;
  discussion_end_date: string | null;
  comments_total: number | null;
  likes_count: number | null;
  dislikes_count: number | null;
  first_seen_at: string;
  last_checked_at: string;
}

export interface Comment {
  id: number;
  external_comment_id: number;
  parent_external_comment_id: number | null;
  author_name: string | null;
  body: string;
  article_ref: string | null;
  status: string | null;
  commented_at_raw: string | null;
  first_seen_at: string;
}

export interface DocumentDetail extends DocumentListItem {
  comments: Comment[];
}

export interface SectionCount {
  section: string;
  count: number;
}

export interface StatusCount {
  status: string | null;
  count: number;
}

export interface AnalyticsSummary {
  documents_by_section: SectionCount[];
  documents_by_status: StatusCount[];
  total_documents: number;
  total_comments: number;
}

export interface TimeseriesPoint {
  bucket: string;
  count: number;
}

export interface CrawlStatusCount {
  page_type: string;
  status: string;
  count: number;
}

export interface CrawlError {
  url: string;
  page_type: string;
  last_error: string | null;
  processed_at: string | null;
}

export interface CrawlStatus {
  counts: CrawlStatusCount[];
  last_processed_at: string | null;
  recent_errors: CrawlError[];
}
