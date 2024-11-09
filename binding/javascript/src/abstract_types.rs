// /// import the preludes
// use napi::{bindgen_prelude::*, JsBuffer, JsObject};
// use napi_derive::napi;
// use raftify::{async_trait, AbstractStateMachine};

// #[napi]
// pub struct JsFSM {
//     inner: JsObject,
// }

// async fn promise_to_future(promise: JsObject) -> Result<JsUnknown> {
//     let (deferred, promise_future) = napi::futures::Promise::new(promise.env)?;
//     let then_fn: JsFunction = promise.get_named_property("then")?;
//     let catch_fn: JsFunction = promise.get_named_property("catch")?;

//     then_fn.call_with_this(
//         &promise,
//         (deferred.resolve,),
//     )?;
//     catch_fn.call_with_this(
//         &promise,
//         (deferred.reject,),
//     )?;

//     promise_future.await
// }

// impl AbstractStateMachine for JsFSM {
//     async fn apply(&mut self, log_entry: Vec<u8>) -> Result<Vec<u8>> {
//         let apply_fn: JsFunction = self.inner.get_named_property("apply")?;
//         let log_entry_buffer = Buffer::from(log_entry);

//         // Pass the buffer directly as argument
//         let args = &[log_entry_buffer];
//         let promise_unknown = apply_fn.call(Some(&self.inner), args)?;

//         let promise = promise_unknown.coerce_to_object()?;

//         let result_unknown = promise_to_future(promise).await?;
//         let result_buffer: Buffer = result_unknown.try_into()?;
//         Ok(result_buffer.to_vec())
//     }

//     async fn snapshot(&self) -> Result<Vec<u8>> {
//         let snapshot_fn: JsFunction = self.inner.get_named_property("snapshot")?;

//         let promise: JsObject = snapshot_fn.call(None, &[])?;
//         let result = promise_to_future(promise).await?;
//         let result_buffer: JsBuffer = result.try_into()?;
//         Ok(result_buffer.into_value()?)
//     }

//     async fn restore(&mut self, snapshot: Vec<u8>) -> Result<()> {
//         let restore_fn: JsFunction = self.inner.get_named_property("restore")?;
//         let snapshot_buffer = JsBuffer::from_slice(&snapshot)?;

//         let promise: JsObject = restore_fn.call(
//             None,
//             &[snapshot_buffer.into_unknown()],
//         )?;

//         promise_to_future(promise).await?;
//         Ok(())
//     }

//     fn encode(&self) -> Result<Vec<u8>> {
//         let encode_fn: JsFunction = self.inner.get_named_property("encode")?;
//         let result = encode_fn.call(None, &[])?;
//         let buffer: JsBuffer = result.try_into()?;
//         Ok(buffer.into_value()?)
//     }

//     fn decode(data: &[u8]) -> Result<Self> {
//         let global = get_global()?;
//         let decode_fn: JsFunction = global.get_named_property("decodeFSM")?;
//         let data_buffer = JsBuffer::from_slice(data)?;

//         let js_object = decode_fn.call(None, &[data_buffer.into_unknown()])?;
//         let js_fsm = js_object.coerce_to_object()?;

//         Ok(JsFSM { inner: js_fsm })
//     }
// }
