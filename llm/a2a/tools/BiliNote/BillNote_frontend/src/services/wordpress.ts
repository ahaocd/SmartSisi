import request from '@/utils/request'
import toast from 'react-hot-toast'

export interface PublishToWordPressParams {
  title: string
  content: string
  status?: 'draft' | 'publish'
  provider_id?: string
  model_name?: string
}

export interface PublishResult {
  success: boolean
  post_id?: number
  post_url?: string
  title?: string
  category?: string
  error?: string
}

/**
 * 发布单篇文章到 WordPress
 */
export const publishToWordPress = async (params: PublishToWordPressParams): Promise<PublishResult> => {
  try {
    const response = await request.post('/wordpress/publish/single', params)
    
    if (response.success) {
      toast.success('文章发布成功！')
    } else {
      toast.error(response.error || '发布失败')
    }
    
    return response
  } catch (e: any) {
    console.error('❌ WordPress 发布失败', e)
    toast.error('发布失败，请检查 WordPress 配置')
    throw e
  }
}

/**
 * 获取 WordPress 分类列表
 */
export const getWordPressCategories = async () => {
  try {
    return await request.get('/wordpress/categories')
  } catch (e) {
    console.error('❌ 获取分类失败', e)
    throw e
  }
}
