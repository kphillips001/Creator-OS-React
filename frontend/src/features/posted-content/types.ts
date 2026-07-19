export type PostedContentItem = {
  contentId: string;
  platform: "X" | "Telegram" | "Fanvue" | string;
  postedAt: string;
  caption: string;
  creator: string;
  creatorProfileId: number | null;
  generationLibraryId: string;
  provider: string;
  prompt: string;
  fileLocation: string;
  mediaUrl: string;
};
