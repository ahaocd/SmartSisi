import request from '@/utils/request'
import toast from 'react-hot-toast'

export const generateNote = async (data: {
  video_url: string
  platform: string
  quality: string
  model_name: string
  provider_id: string
  task_id?: string
  format: Array<string>
  style: string
  extras?: string
  video_understand?: boolean
  video_interval?: number
  grid_size: Array<number>
}) => {
  try {
    console.log('generateNote', data)
    const response = await request.post('/generate_note', data)

    if (!response) {
      if (response.data.msg) {
        toast.error(response.data.msg)
      }
      return null
    }
    toast.success('笔记生成任务已提交！')

    console.log('res', response)
    // 成功提示

    return response
  } catch (e: any) {
    console.error('❌ 请求出错', e)

    // 错误提示
    // toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}

export const delete_task = async ({ video_id, platform }) => {
  try {
    const data = {
      video_id,
      platform,
    }
    const res = await request.post('/delete_task', data)


      toast.success('任务已成功删除')
      return res
  } catch (e) {
    toast.error('请求异常，删除任务失败')
    console.error('❌ 删除任务失败:', e)
    throw e
  }
}

export const get_task_status = async (task_id: string) => {
  try {
    // 成功提示

    return await request.get('/task_status/' + task_id)
  } catch (e) {
    console.error('❌ 请求出错', e)

    // 错误提示
    toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}

/**
 * 批量生成笔记并自动发布到 WordPress
 * 一键处理多个视频链接，全自动
 */
export const batchGenerateAndPublish = async (data: {
  video_urls: string[]  // 多个视频链接
  platform: string
  quality: string
  model_name: string
  provider_id: string
  format: Array<string>
  style: string
  extras?: string
  auto_publish: boolean  // true=直接发布，false=存草稿
}) => {
  try {
    console.log('batchGenerateAndPublish', data)
    const response = await request.post('/batch_generate_publish', data)
    
    if (response) {
      toast.success(`批量任务已提交！共 ${data.video_urls.length} 个视频`)
    }
    
    return response
  } catch (e: any) {
    console.error('❌ 批量任务提交失败', e)
    toast.error('批量任务提交失败')
    throw e
  }
}

/**
 * 获取批量任务状态
 */
export const getBatchTaskStatus = async (batch_id: string) => {
  try {
    return await request.get('/batch_status/' + batch_id)
  } catch (e) {
    console.error('❌ 获取批量状态失败', e)
    throw e
  }
}
