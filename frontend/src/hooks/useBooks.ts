"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { getSupabaseBrowser } from "@/lib/supabase-browser"
import { useAuthContext } from "@/components/AuthProvider"
import type { Book, BookMetadata, DashboardStats } from "@/lib/types"

const CACHE_KEY = "scrpt-books"

/** Strip heavy fields (like artwork) for localStorage cache */
function stripForCache(books: Book[]): Book[] {
  return books.map((b) => ({
    ...b,
    data: { ...b.data },
  }))
}

function loadCache(): Book[] {
  if (typeof window === "undefined") return []
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveCache(books: Book[]) {
  if (typeof window === "undefined") return
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(stripForCache(books)))
  } catch {
    // localStorage full — silently ignore
  }
}

export function useBooks() {
  const { user } = useAuthContext()
  const [books, setBooks] = useState<Book[]>(loadCache)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const fetchedRef = useRef(false)

  // Fetch from Supabase and merge
  const fetchBooks = useCallback(async () => {
    const supabase = getSupabaseBrowser()
    if (!supabase || !user) return

    try {
      const { data, error: err } = await supabase
        .from("books")
        .select("*")
        .order("created_at", { ascending: false })

      if (err) throw new Error(err.message)

      const fetched = (data || []).map((row: Record<string, unknown>) => ({
        id: row.id as string,
        catalog_number: row.catalog_number as string,
        title: row.title as string,
        status: row.status as string,
        data: (row.data || {}) as BookMetadata,
        created_at: row.created_at as string,
        updated_at: row.updated_at as string,
      })) as Book[]

      setBooks(fetched)
      saveCache(fetched)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [user])

  // Initial fetch
  useEffect(() => {
    if (!user || fetchedRef.current) return
    fetchedRef.current = true
    fetchBooks()
  }, [user, fetchBooks])

  // Generate next catalog number
  const getNextCatalogNumber = useCallback((): string => {
    if (books.length === 0) return "SC-001"
    const nums = books
      .map((b) => {
        const m = b.catalog_number.match(/SC-(\d+)/)
        return m ? parseInt(m[1]) : 0
      })
      .filter((n) => n > 0)
    const max = nums.length > 0 ? Math.max(...nums) : 0
    return `SC-${String(max + 1).padStart(3, "0")}`
  }, [books])

  // Create a book
  const createBook = useCallback(
    async (input: {
      title: string
      book_type: string
      subtitle?: string
      trim_size?: string
      paper_type?: string
      page_count?: number
      author_name?: string
      list_price?: number
      niche_keyword?: string
      generator_config?: Record<string, unknown>
    }): Promise<Book | null> => {
      const supabase = getSupabaseBrowser()
      if (!supabase || !user) return null

      const catalogNumber = getNextCatalogNumber()
      const bookData: Record<string, unknown> = {
        book_type: input.book_type,
        trim_size: input.trim_size || "8.5x11",
        paper_type: input.paper_type || "white_bw",
        page_count: input.page_count || 100,
        subtitle: input.subtitle || "",
        author_name: input.author_name || "",
        description: "",
        keywords: [],
        categories: [],
        list_price: input.list_price || 9.99,
        currency: "USD",
        interior_pdf: null,
        cover_pdf: null,
        cover_front_png: null,
        quality_score: null,
        quality_report: null,
        ai_vision_score: null,
        dimension_check_passed: null,
        asin: null,
        kdp_id: null,
        bsr: null,
        niche_keyword: input.niche_keyword || null,
        niche_id: null,
        generator_config: input.generator_config || {},
      }

      const { data, error: err } = await supabase
        .from("books")
        .insert({
          user_id: user.id,
          catalog_number: catalogNumber,
          title: input.title,
          status: "draft",
          data: bookData,
        })
        .select()
        .single()

      if (err) throw new Error(err.message)

      const newBook: Book = {
        id: data.id,
        catalog_number: data.catalog_number,
        title: data.title,
        status: data.status,
        data: data.data as BookMetadata,
        created_at: data.created_at,
        updated_at: data.updated_at,
      }

      setBooks((prev) => {
        const updated = [newBook, ...prev]
        saveCache(updated)
        return updated
      })

      return newBook
    },
    [user, getNextCatalogNumber]
  )

  // Update a book
  const updateBook = useCallback(
    async (
      id: string,
      updates: Partial<{
        title: string
        status: string
        data: Partial<BookMetadata>
      }>
    ): Promise<Book | null> => {
      const supabase = getSupabaseBrowser()
      if (!supabase || !user) return null

      const existing = books.find((b) => b.id === id)
      if (!existing) return null

      const patch: Record<string, unknown> = {}
      if (updates.title) patch.title = updates.title
      if (updates.status) patch.status = updates.status
      if (updates.data) {
        patch.data = { ...existing.data, ...updates.data }
      }

      const { data, error: err } = await supabase
        .from("books")
        .update(patch)
        .eq("id", id)
        .select()
        .single()

      if (err) throw new Error(err.message)

      const updated: Book = {
        id: data.id,
        catalog_number: data.catalog_number,
        title: data.title,
        status: data.status,
        data: data.data as BookMetadata,
        created_at: data.created_at,
        updated_at: data.updated_at,
      }

      setBooks((prev) => {
        const next = prev.map((b) => (b.id === id ? updated : b))
        saveCache(next)
        return next
      })

      return updated
    },
    [user, books]
  )

  // Delete a book
  const deleteBook = useCallback(
    async (id: string): Promise<boolean> => {
      const supabase = getSupabaseBrowser()
      if (!supabase || !user) return false

      const { error: err } = await supabase.from("books").delete().eq("id", id)

      if (err) throw new Error(err.message)

      setBooks((prev) => {
        const next = prev.filter((b) => b.id !== id)
        saveCache(next)
        return next
      })

      return true
    },
    [user]
  )

  // Get a single book by ID
  const getBook = useCallback(
    (id: string): Book | undefined => {
      return books.find((b) => b.id === id)
    },
    [books]
  )

  // Compute dashboard stats from local books array
  const dashboardStats: DashboardStats = {
    total_books: books.length,
    books_by_status: books.reduce(
      (acc, b) => {
        acc[b.status] = (acc[b.status] || 0) + 1
        return acc
      },
      {} as Record<string, number>
    ),
    books_live: books.filter((b) => b.status === "live").length,
    books_in_progress: books.filter((b) =>
      ["generating", "quality_check", "uploading"].includes(b.status)
    ).length,
    total_niches: 0,
    validated_niches: 0,
    estimated_monthly_revenue: 0,
    average_bsr: null,
    recent_books: books.slice(0, 8),
    recent_niches: [],
  }

  return {
    books,
    loading,
    error,
    dashboardStats,
    fetchBooks,
    createBook,
    updateBook,
    deleteBook,
    getBook,
    getNextCatalogNumber,
  }
}
