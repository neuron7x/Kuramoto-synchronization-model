/**
 * Community Store
 * State management for community view with filters and pagination
 */

export interface CommunityActivity {
  id: string;
  type: 'contribution' | 'event' | 'champion' | 'opportunity';
  category: string;
  title: string;
  description?: string;
  timestamp: string;
  geography?: string;
  user?: {
    id: string;
    name: string;
    avatar?: string;
  };
  metadata?: Record<string, unknown>;
}

export interface CommunityFilters {
  type: string[];
  category: string[];
  geography: string[];
  dateRange?: {
    start: string;
    end: string;
  };
}

export interface PaginationState {
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
}

export interface CommunityStoreState {
  activities: CommunityActivity[];
  filters: CommunityFilters;
  pagination: PaginationState;
  loading: boolean;
  error: Error | null;
}

export type CommunityStoreListener = (state: CommunityStoreState) => void;

export class CommunityStore {
  private state: CommunityStoreState;
  private listeners: Set<CommunityStoreListener>;

  constructor(initialActivities: CommunityActivity[] = []) {
    this.state = {
      activities: initialActivities,
      filters: {
        type: [],
        category: [],
        geography: [],
      },
      pagination: {
        page: 1,
        pageSize: 20,
        totalItems: initialActivities.length,
        totalPages: Math.ceil(initialActivities.length / 20),
      },
      loading: false,
      error: null,
    };
    this.listeners = new Set();
  }

  /**
   * Get current state
   */
  getState(): CommunityStoreState {
    return { ...this.state };
  }

  /**
   * Subscribe to state changes
   */
  subscribe(listener: CommunityStoreListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /**
   * Notify all listeners
   */
  private notify(): void {
    this.listeners.forEach((listener) => {
      try {
        listener(this.getState());
      } catch (error) {
        console.error('Error in store listener:', error);
      }
    });
  }

  /**
   * Update state
   */
  private setState(updates: Partial<CommunityStoreState>): void {
    this.state = { ...this.state, ...updates };
    this.notify();
  }

  /**
   * Set activities
   */
  setActivities(activities: CommunityActivity[]): void {
    const totalItems = activities.length;
    const totalPages = Math.ceil(totalItems / this.state.pagination.pageSize);
    
    this.setState({
      activities,
      pagination: {
        ...this.state.pagination,
        totalItems,
        totalPages,
        page: Math.min(this.state.pagination.page, totalPages || 1),
      },
    });
  }

  /**
   * Add activity
   */
  addActivity(activity: CommunityActivity): void {
    const activities = [activity, ...this.state.activities];
    this.setActivities(activities);
  }

  /**
   * Update activity
   */
  updateActivity(id: string, updates: Partial<CommunityActivity>): void {
    const activities = this.state.activities.map((activity) =>
      activity.id === id ? { ...activity, ...updates } : activity
    );
    this.setActivities(activities);
  }

  /**
   * Remove activity
   */
  removeActivity(id: string): void {
    const activities = this.state.activities.filter((activity) => activity.id !== id);
    this.setActivities(activities);
  }

  /**
   * Set filters
   */
  setFilters(filters: Partial<CommunityFilters>): void {
    this.setState({
      filters: {
        ...this.state.filters,
        ...filters,
      },
      pagination: {
        ...this.state.pagination,
        page: 1, // Reset to first page when filters change
      },
    });
  }

  /**
   * Clear filters
   */
  clearFilters(): void {
    this.setState({
      filters: {
        type: [],
        category: [],
        geography: [],
      },
      pagination: {
        ...this.state.pagination,
        page: 1,
      },
    });
  }

  /**
   * Set page
   */
  setPage(page: number): void {
    const validPage = Math.max(1, Math.min(page, this.state.pagination.totalPages));
    this.setState({
      pagination: {
        ...this.state.pagination,
        page: validPage,
      },
    });
  }

  /**
   * Set page size
   */
  setPageSize(pageSize: number): void {
    const totalPages = Math.ceil(this.state.pagination.totalItems / pageSize);
    this.setState({
      pagination: {
        ...this.state.pagination,
        pageSize,
        totalPages,
        page: Math.min(this.state.pagination.page, totalPages || 1),
      },
    });
  }

  /**
   * Get filtered activities
   */
  getFilteredActivities(): CommunityActivity[] {
    let filtered = this.state.activities;

    // Apply type filter
    if (this.state.filters.type.length > 0) {
      filtered = filtered.filter((activity) =>
        this.state.filters.type.includes(activity.type)
      );
    }

    // Apply category filter
    if (this.state.filters.category.length > 0) {
      filtered = filtered.filter((activity) =>
        this.state.filters.category.some((cat) =>
          activity.category.toLowerCase().includes(cat.toLowerCase())
        )
      );
    }

    // Apply geography filter
    if (this.state.filters.geography.length > 0) {
      filtered = filtered.filter((activity) =>
        activity.geography && this.state.filters.geography.includes(activity.geography)
      );
    }

    // Apply date range filter
    if (this.state.filters.dateRange) {
      const { start, end } = this.state.filters.dateRange;
      filtered = filtered.filter((activity) => {
        const timestamp = new Date(activity.timestamp).getTime();
        const startTime = new Date(start).getTime();
        const endTime = new Date(end).getTime();
        return timestamp >= startTime && timestamp <= endTime;
      });
    }

    return filtered;
  }

  /**
   * Get paginated activities
   */
  getPaginatedActivities(): CommunityActivity[] {
    const filtered = this.getFilteredActivities();
    const { page, pageSize } = this.state.pagination;
    const start = (page - 1) * pageSize;
    const end = start + pageSize;
    return filtered.slice(start, end);
  }

  /**
   * Get filter options from activities
   */
  getFilterOptions(): {
    types: string[];
    categories: string[];
    geographies: string[];
  } {
    const types = new Set<string>();
    const categories = new Set<string>();
    const geographies = new Set<string>();

    this.state.activities.forEach((activity) => {
      types.add(activity.type);
      if (activity.category) {
        categories.add(activity.category);
      }
      if (activity.geography) {
        geographies.add(activity.geography);
      }
    });

    return {
      types: Array.from(types).sort(),
      categories: Array.from(categories).sort(),
      geographies: Array.from(geographies).sort(),
    };
  }

  /**
   * Get segmented activities
   */
  getSegmentedActivities(): Record<string, CommunityActivity[]> {
    const filtered = this.getFilteredActivities();
    const segments: Record<string, CommunityActivity[]> = {
      champions: [],
      events: [],
      opportunities: [],
      contributions: [],
    };

    filtered.forEach((activity) => {
      switch (activity.type) {
        case 'champion':
          segments.champions.push(activity);
          break;
        case 'event':
          segments.events.push(activity);
          break;
        case 'opportunity':
          segments.opportunities.push(activity);
          break;
        case 'contribution':
          segments.contributions.push(activity);
          break;
        default:
          segments.contributions.push(activity);
      }
    });

    return segments;
  }

  /**
   * Set loading state
   */
  setLoading(loading: boolean): void {
    this.setState({ loading });
  }

  /**
   * Set error
   */
  setError(error: Error | null): void {
    this.setState({ error });
  }

  /**
   * Clear error
   */
  clearError(): void {
    this.setState({ error: null });
  }
}

// Singleton instance
let defaultStore: CommunityStore | null = null;

export function getCommunityStore(activities?: CommunityActivity[]): CommunityStore {
  if (!defaultStore) {
    defaultStore = new CommunityStore(activities);
  }
  return defaultStore;
}

export function resetCommunityStore(): void {
  defaultStore = null;
}
