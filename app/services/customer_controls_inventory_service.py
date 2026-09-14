"""Provider-neutral read model; never creates identities or controls."""
from app.repositories.customer_controls_inventory_repository import CustomerControlsInventoryRepository
class CustomerControlsInventoryService:
 def __init__(self,repository=None):self.repository=repository or CustomerControlsInventoryRepository()
 def list(self,*,creator_profile_id,fanvue_account_id,search='',filter='ALL',sort='LATEST_ACTIVITY',page=1,page_size=100):
  rows=[dict(r) for r in self.repository.rows(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)]
  # Eligibility is supplied by the backend repository.  Keep this defensive
  # boundary so search and provider filters can never resurrect an ineligible
  # canonical provider customer from a custom repository snapshot.
  rows=[r for r in rows if r.get('operational_eligibility_reason')]
  term=search.strip().casefold()
  if term:
   if term.isdigit():rows=[r for r in rows if term in (str(r.get('telegram_user_id') or ''),str(r.get('x_numeric_id') or ''))]
   else:rows=[r for r in rows if term in ' '.join(str(r.get(k) or '') for k in ('display_name','best_username','telegram_username','telegram_display_name','x_username','fanvue_handle')).casefold()]
  predicates={'ALL':lambda r:True,'BUYERS':lambda r:int(r.get('purchase_count') or 0)>0,'PROSPECTS':lambda r:r['row_kind']=='TELEGRAM_PROSPECT','TELEGRAM':lambda r:r.get('telegram_status')!='NOT_OBSERVED','FANVUE':lambda r:r['row_kind']=='CANONICAL_CUSTOMER','X':lambda r:r.get('x_status')=='VERIFIED'}
  selected=str(filter).upper()
  if selected not in predicates:raise ValueError('Unsupported inventory filter')
  rows=[r for r in rows if predicates[selected](r)]
  if str(sort).upper()=='LIFETIME_SPEND':rows.sort(key=lambda r:int(r.get('lifetime_gross_minor') or 0),reverse=True)
  start=(max(1,page)-1)*page_size;items=rows[start:start+page_size]
  return {'items':[self._project(r) for r in items],'total':len(rows),'page':page,'pageSize':page_size}
 @staticmethod
 def _project(r):
  canonical=r['row_kind']=='CANONICAL_CUSTOMER';available=r['control_availability']=='AVAILABLE'
  spend=r.get('lifetime_gross_minor'); purchases=int(r.get('purchase_count') or 0)
  return {'rowKey':r['row_key'],'personKey':r['row_key'],'rowKind':r['row_kind'],'operationalEligibilityReason':r['operational_eligibility_reason'],'localFanvueUserId':r.get('local_fanvue_user_id'),'displayName':r['display_name'],'username':r.get('best_username'),'metadataComplete':bool(r.get('canonical_username') and r.get('canonical_display_name') and r.get('canonical_source')),'providerEvidenceAvailable':canonical and not bool(r.get('canonical_username') and r.get('canonical_display_name')),'platforms':{'fanvue':'CANONICAL' if canonical else 'NOT_VERIFIED','telegram':r['telegram_status'],'x':r['x_status']},'telegramObservation':{'sources':list(r.get('observation_sources') or []),'sourceChannelId':r.get('source_channel_id'),'privateChatEstablished':r.get('private_chat_id') is not None,'participantStatus':r.get('participant_status')},'identityStatus':'MAPPED_VERIFIED' if r['telegram_status']=='VERIFIED' else r['telegram_status'],'buyerStatus':'BUYER' if purchases>0 else 'PROSPECT','isBuyer':purchases>0,'commerce':{'lifetimeGrossMinor':spend,'lifetimeNetMinor':r.get('lifetime_net_minor'),'purchaseCount':purchases,'firstPurchaseAt':r.get('first_purchase_at'),'lastPurchaseAt':r.get('last_purchase_at'),'lastSyncedAt':r.get('last_synced_at'),'ownedAssetCount':int(r.get('owned_asset_count') or 0)},'lifetimeVerifiedRevenueMinor':spend,'qualifyingPurchaseCount':purchases,'controlAvailability':r['control_availability'],'controls':None if not available else {'avaChatEnabled':r.get('mode')!='HUMAN_OPERATOR','contentSellingEnabled':bool(r.get('content_selling_enabled')),'sessionSellingEnabled':bool(r.get('session_selling_enabled'))},'relationshipKey':r.get('relationship_key'),'hasConversation':bool(r.get('relationship_key')),'telegramUserId':r.get('telegram_user_id'),'xNumericId':r.get('x_numeric_id'),'xLinkId':str(r['x_link_id']) if r.get('x_link_id') else None,'latestActivityAt':r.get('latest_activity_at'),'activePurchaseIntent':False,'activeSalesSession':False}
